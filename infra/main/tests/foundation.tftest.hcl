mock_provider "aws" {
  # The provider checks that these attributes look like ARNs, so the generated strings are not enough.
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/mock"
    }
  }

  # key_name is computed, so the mock would invent one. No key pair is configured; empty stands for none.
  mock_resource "aws_instance" {
    defaults = {
      key_name = ""
    }
  }

  mock_resource "aws_iam_openid_connect_provider" {
    defaults = {
      arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
    }
  }

  override_data {
    target = data.aws_caller_identity.current
    values = {
      account_id = "123456789012"
    }
  }

  override_data {
    target = data.aws_availability_zones.available
    values = {
      names = ["eu-west-1a", "eu-west-1b"]
    }
  }

  override_data {
    target = data.aws_ssm_parameter.al2023_arm64
    values = {
      insecure_value = "ami-0123456789abcdef0"
    }
  }

  # Ticket 025's prefix list; the same override is in backend.tftest.hcl. (The CloudFront policy
  # data sources need none: a mock cannot set their id, and only their names are checked.)
  override_data {
    target = data.aws_ec2_managed_prefix_list.cloudfront
    values = {
      id = "pl-4fa04526"
      entries = [
        { cidr = "130.176.0.0/18", description = "mock" },
        { cidr = "15.158.0.0/16", description = "mock" },
      ]
    }
  }
}

variables {
  region            = "eu-west-1"
  aws_account_id    = "123456789012"
  owner_email       = "owner@example.com"
  github_repository = "someone/cragmatch"
}

run "budget_alerts_the_owner_at_both_thresholds" {
  command = apply

  assert {
    condition = (
      aws_budgets_budget.monthly.budget_type == "COST"
      && aws_budgets_budget.monthly.time_unit == "MONTHLY"
      && aws_budgets_budget.monthly.limit_amount == "11.2"
      && aws_budgets_budget.monthly.limit_unit == "USD"
    )
    error_message = "The budget must be a monthly COST budget of 11.2 USD."
  }

  assert {
    condition     = length(aws_budgets_budget.monthly.notification) == 3
    error_message = "There must be three notifications."
  }

  assert {
    condition = alltrue([
      for n in aws_budgets_budget.monthly.notification :
      n.subscriber_email_addresses == toset(["owner@example.com"])
    ])
    error_message = "Every notification must go to the owner."
  }

  assert {
    condition = toset([
      for n in aws_budgets_budget.monthly.notification : "${n.notification_type}-${n.threshold}"
    ]) == toset(["ACTUAL-50", "ACTUAL-100", "FORECASTED-100"])
    error_message = "Expected ACTUAL at 50, ACTUAL at 100 and FORECASTED at 100."
  }
}

run "budget_counts_cost_before_credits" {
  command = apply

  assert {
    condition     = one(aws_budgets_budget.monthly.cost_types).include_credit == false
    error_message = "Credits must not be subtracted from the budget."
  }
}

run "owner_email_must_be_an_address" {
  command = plan

  variables {
    owner_email = "nope"
  }

  expect_failures = [var.owner_email]
}

run "network_has_one_public_subnet_in_the_region" {
  command = apply

  assert {
    condition     = aws_vpc.main.enable_dns_hostnames == true
    error_message = "The VPC needs DNS hostnames."
  }

  assert {
    condition     = aws_subnet.public.availability_zone == "eu-west-1a" && aws_subnet.public.map_public_ip_on_launch == false
    error_message = "The subnet must be in the first zone and not hand out public addresses."
  }

  assert {
    condition = anytrue([
      for r in aws_route_table.public.route : r.cidr_block == "0.0.0.0/0" && r.gateway_id == aws_internet_gateway.main.id
    ])
    error_message = "The route table must send 0.0.0.0/0 to the internet gateway."
  }
}

run "region_must_be_in_europe" {
  command = plan

  variables {
    region = "us-east-1"
  }

  expect_failures = [var.region]
}

run "host_allows_web_traffic_out_only" {
  command = apply

  assert {
    condition = (
      aws_vpc_security_group_egress_rule.https_out.ip_protocol == "tcp"
      && aws_vpc_security_group_egress_rule.https_out.from_port == 443
      && aws_vpc_security_group_egress_rule.https_out.to_port == 443
      && aws_vpc_security_group_egress_rule.https_out.cidr_ipv4 == "0.0.0.0/0"
    )
    error_message = "One outbound rule is TCP 443 to 0.0.0.0/0."
  }

  assert {
    condition = (
      aws_vpc_security_group_egress_rule.http_out.ip_protocol == "tcp"
      && aws_vpc_security_group_egress_rule.http_out.from_port == 80
      && aws_vpc_security_group_egress_rule.http_out.to_port == 80
      && aws_vpc_security_group_egress_rule.http_out.cidr_ipv4 == "0.0.0.0/0"
    )
    error_message = "The other outbound rule is TCP 80 (apt repositories) to 0.0.0.0/0."
  }

  assert {
    condition     = length(aws_security_group.host.ingress) == 0 && length(aws_security_group.host.egress) == 0
    error_message = "The host security group must have no inline rules, so there is no inbound rule."
  }

  assert {
    condition     = length(aws_default_security_group.default.ingress) == 0 && length(aws_default_security_group.default.egress) == 0
    error_message = "The default security group must have no rules."
  }
}

run "host_is_hardened" {
  command = apply

  assert {
    condition = (
      one(aws_instance.host.metadata_options).http_tokens == "required"
      && one(aws_instance.host.metadata_options).http_put_response_hop_limit == 1
    )
    error_message = "IMDSv2 only, with hop limit 1."
  }

  assert {
    condition     = aws_instance.host.key_name == null || aws_instance.host.key_name == ""
    error_message = "The host must have no key pair."
  }

  assert {
    condition     = one(aws_instance.host.credit_specification).cpu_credits == "standard"
    error_message = "CPU credits must be standard."
  }

  assert {
    condition     = one(aws_instance.host.root_block_device).volume_type == "gp3" && one(aws_instance.host.root_block_device).encrypted == true
    error_message = "The root volume must be encrypted gp3."
  }

  assert {
    condition     = aws_instance.host.user_data_replace_on_change == true
    error_message = "A changed boot script must replace the host."
  }

  assert {
    condition     = aws_instance.host.instance_type == "t4g.small"
    error_message = "The default instance type is t4g.small."
  }
}

run "instance_type_must_be_graviton" {
  command = plan

  variables {
    instance_type = "t3.small"
  }

  expect_failures = [var.instance_type]
}

run "data_volume_is_encrypted_in_the_hosts_zone" {
  command = apply

  assert {
    condition = (
      aws_ebs_volume.data.type == "gp3"
      && aws_ebs_volume.data.encrypted == true
      && aws_ebs_volume.data.size == 4
      && aws_ebs_volume.data.availability_zone == aws_subnet.public.availability_zone
      && aws_ebs_volume.data.tags["Backup"] == "cragmatch-daily"
    )
    error_message = "The data volume must be encrypted gp3, 4 GiB, in the subnet's zone, tagged for backup."
  }

  assert {
    condition     = aws_volume_attachment.data.stop_instance_before_detaching == true
    error_message = "The host must stop before the volume is detached."
  }
}

run "data_volume_is_snapshotted_daily_and_kept_a_week" {
  command = apply

  assert {
    condition = (
      one(aws_dlm_lifecycle_policy.db.policy_details).target_tags["Backup"] == "cragmatch-daily"
      && one(one(aws_dlm_lifecycle_policy.db.policy_details).resource_types) == "VOLUME"
    )
    error_message = "The policy must target the backup tag on volumes."
  }

  assert {
    condition = (
      one(one(aws_dlm_lifecycle_policy.db.policy_details).schedule).copy_tags == true
      && one(one(one(aws_dlm_lifecycle_policy.db.policy_details).schedule).create_rule).interval == 24
      && one(one(one(aws_dlm_lifecycle_policy.db.policy_details).schedule).create_rule).interval_unit == "HOURS"
      && one(one(one(aws_dlm_lifecycle_policy.db.policy_details).schedule).retain_rule).count == 7
    )
    error_message = "Snapshots every 24 hours, kept 7, with tags copied."
  }
}

run "ebs_is_encrypted_by_default" {
  command = apply

  assert {
    condition     = aws_ebs_encryption_by_default.this.enabled == true
    error_message = "EBS encryption by default must be on."
  }
}

run "db_password_is_a_write_only_secure_string" {
  command = apply

  assert {
    condition = (
      aws_ssm_parameter.db_password.name == "/cragmatch/db/password"
      && aws_ssm_parameter.db_password.type == "SecureString"
      && aws_ssm_parameter.db_password.value_wo_version == 1
    )
    error_message = "A SecureString at /cragmatch/db/password, version 1."
  }

  assert {
    condition     = aws_ssm_parameter.db_password.value_wo == null
    error_message = "A write-only value must not be readable from the resource."
  }
}

run "user_data_names_secrets_but_holds_none" {
  command = apply

  assert {
    condition     = strcontains(local.user_data, "/cragmatch/db/password")
    error_message = "The boot data must name the password parameter."
  }

  assert {
    condition = anytrue([
      for f in yamldecode(trimprefix(local.user_data, "#cloud-config\n")).write_files :
      f.path == "/opt/cragmatch/db/Dockerfile" && f.content == file("host/db/Dockerfile")
    ])
    error_message = "The boot data must carry the exact database Dockerfile."
  }

  assert {
    condition = anytrue([
      for f in yamldecode(trimprefix(local.user_data, "#cloud-config\n")).write_files :
      f.path == "/opt/cragmatch/cragmatch-db.service" && f.content == file("host/cragmatch-db.service")
    ])
    error_message = "The boot data must carry the exact unit file."
  }

  assert {
    # The setup script legitimately contains "POSTGRES_PASSWORD=%s"; what must never appear is a
    # value assigned to it. The underlying guarantee is that Terraform refuses an ephemeral value
    # (the generated password) in user_data.
    condition     = !can(regex("POSTGRES_PASSWORD=[A-Za-z0-9]", local.user_data))
    error_message = "The boot data must not assign a literal value to POSTGRES_PASSWORD."
  }

  assert {
    condition     = length(aws_instance.host.user_data_base64) < 16384
    error_message = "EC2 user data is limited to 16384 bytes."
  }
}

run "host_role_reads_only_cragmatch_parameters" {
  command = apply

  assert {
    condition = (
      jsondecode(aws_iam_role_policy.host_parameters.policy).Statement[0].Action == ["ssm:GetParameter", "ssm:GetParameters"]
      && jsondecode(aws_iam_role_policy.host_parameters.policy).Statement[0].Resource == "arn:aws:ssm:eu-west-1:123456789012:parameter/cragmatch/*"
    )
    error_message = "The host may only read parameters under /cragmatch/."
  }
}

run "deploy_role_trusts_only_this_repository_and_branch" {
  command = apply

  assert {
    condition     = jsondecode(aws_iam_role.github_deploy.assume_role_policy).Statement[0].Principal.Federated == aws_iam_openid_connect_provider.github.arn
    error_message = "The trust must name the GitHub provider."
  }

  assert {
    condition = (
      jsondecode(aws_iam_role.github_deploy.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
      && jsondecode(aws_iam_role.github_deploy.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:someone/cragmatch:ref:refs/heads/main"
    )
    error_message = "The trust must match audience and exactly this repository's main branch."
  }

  assert {
    condition     = !contains(keys(jsondecode(aws_iam_role.github_deploy.assume_role_policy).Statement[0].Condition), "StringLike")
    error_message = "The trust must not use StringLike."
  }

  assert {
    condition     = aws_iam_openid_connect_provider.github.url == "https://token.actions.githubusercontent.com" && aws_iam_openid_connect_provider.github.client_id_list == toset(["sts.amazonaws.com"])
    error_message = "The provider URL and client id must be GitHub's and sts.amazonaws.com."
  }
}

run "github_repository_must_be_owner_and_name" {
  command = plan

  variables {
    github_repository = "cragmatch"
  }

  expect_failures = [var.github_repository]
}

run "cost_allocation_tag_is_off_until_switched_on" {
  command = apply

  assert {
    condition     = length(aws_ce_cost_allocation_tag.project) == 0
    error_message = "The cost allocation tag must be off by default."
  }
}

run "cost_allocation_tag_activates_project" {
  command = apply

  variables {
    activate_cost_allocation_tag = true
  }

  assert {
    condition     = length(aws_ce_cost_allocation_tag.project) == 1 && aws_ce_cost_allocation_tag.project[0].tag_key == "Project" && aws_ce_cost_allocation_tag.project[0].status == "Active"
    error_message = "With the switch on, the Project tag must be Active."
  }
}
