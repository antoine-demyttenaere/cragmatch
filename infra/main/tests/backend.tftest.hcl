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

  # The two CloudFront policy data sources are not overridden: a mock cannot set their id (the
  # provider reads it from the lookup), so the test checks their names and that the behaviour uses them.
}

variables {
  region            = "eu-west-1"
  aws_account_id    = "123456789012"
  owner_email       = "owner@example.com"
  github_repository = "someone/cragmatch"
}

run "registry_keeps_immutable_tags_and_the_last_five_images" {
  command = apply

  assert {
    condition = (
      aws_ecr_repository.api.name == "cragmatch-api"
      && aws_ecr_repository.api.image_tag_mutability == "IMMUTABLE"
      && one(aws_ecr_repository.api.image_scanning_configuration).scan_on_push == true
    )
    error_message = "The repository must be cragmatch-api, immutable, scanned on push."
  }

  assert {
    condition = (
      jsondecode(aws_ecr_lifecycle_policy.api.policy).rules[0].selection.tagStatus == "untagged"
      && jsondecode(aws_ecr_lifecycle_policy.api.policy).rules[0].selection.countType == "sinceImagePushed"
      && jsondecode(aws_ecr_lifecycle_policy.api.policy).rules[0].selection.countUnit == "days"
      && jsondecode(aws_ecr_lifecycle_policy.api.policy).rules[0].selection.countNumber == 1
      && jsondecode(aws_ecr_lifecycle_policy.api.policy).rules[0].action.type == "expire"
    )
    error_message = "Rule 1 must expire untagged images after one day."
  }

  assert {
    condition = (
      jsondecode(aws_ecr_lifecycle_policy.api.policy).rules[1].selection.tagStatus == "any"
      && jsondecode(aws_ecr_lifecycle_policy.api.policy).rules[1].selection.countType == "imageCountMoreThan"
      && jsondecode(aws_ecr_lifecycle_policy.api.policy).rules[1].selection.countNumber == 5
      && jsondecode(aws_ecr_lifecycle_policy.api.policy).rules[1].action.type == "expire"
    )
    error_message = "Rule 2 must keep the newest five images."
  }
}

run "only_cloudfront_reaches_the_api_port" {
  command = apply

  assert {
    condition = (
      aws_vpc_security_group_ingress_rule.cloudfront_http.ip_protocol == "tcp"
      && aws_vpc_security_group_ingress_rule.cloudfront_http.from_port == 80
      && aws_vpc_security_group_ingress_rule.cloudfront_http.to_port == 80
      && aws_vpc_security_group_ingress_rule.cloudfront_http.prefix_list_id == "pl-4fa04526"
      && aws_vpc_security_group_ingress_rule.cloudfront_http.cidr_ipv4 == null
      && aws_vpc_security_group_ingress_rule.cloudfront_http.security_group_id == aws_security_group.host.id
    )
    error_message = "The one inbound rule is TCP 80 from the CloudFront prefix list, on the host security group."
  }
}

run "api_distribution_passes_every_request_to_the_host" {
  command = apply

  assert {
    condition = (
      length(aws_cloudfront_distribution.api.origin) == 1
      && one(aws_cloudfront_distribution.api.origin).domain_name == aws_eip.host.public_dns
      && one(one(aws_cloudfront_distribution.api.origin).custom_origin_config).origin_protocol_policy == "http-only"
      && one(one(aws_cloudfront_distribution.api.origin).custom_origin_config).http_port == 80
      && one(one(aws_cloudfront_distribution.api.origin).custom_origin_config).origin_read_timeout == 60
      && one(one(aws_cloudfront_distribution.api.origin).custom_origin_config).origin_keepalive_timeout == 4
    )
    error_message = "One origin: the host's DNS name, plain HTTP on port 80, read timeout 60, keep-alive 4."
  }

  assert {
    condition = (
      one(one(aws_cloudfront_distribution.api.origin).custom_header).name == "X-Forwarded-Proto"
      && one(one(aws_cloudfront_distribution.api.origin).custom_header).value == "https"
    )
    error_message = "The origin must receive X-Forwarded-Proto: https."
  }

  assert {
    condition = (
      length(one(aws_cloudfront_distribution.api.default_cache_behavior).allowed_methods) == 7
      && data.aws_cloudfront_cache_policy.caching_disabled.name == "Managed-CachingDisabled"
      && data.aws_cloudfront_origin_request_policy.all_viewer.name == "Managed-AllViewer"
      && one(aws_cloudfront_distribution.api.default_cache_behavior).cache_policy_id == data.aws_cloudfront_cache_policy.caching_disabled.id
      && one(aws_cloudfront_distribution.api.default_cache_behavior).origin_request_policy_id == data.aws_cloudfront_origin_request_policy.all_viewer.id
      && one(aws_cloudfront_distribution.api.default_cache_behavior).viewer_protocol_policy == "redirect-to-https"
    )
    error_message = "All 7 methods, nothing cached, all viewer headers forwarded, https for viewers."
  }

  assert {
    condition = (
      one(aws_cloudfront_distribution.api.viewer_certificate).cloudfront_default_certificate == true
      && aws_cloudfront_distribution.api.is_ipv6_enabled == false
      && aws_cloudfront_distribution.api.price_class == "PriceClass_100"
    )
    error_message = "Default certificate, IPv6 off, PriceClass_100."
  }
}

run "trusted_proxies_are_exactly_the_cloudfront_ranges" {
  command = apply

  assert {
    condition     = strcontains(aws_ssm_parameter.api_settings.value, "FORWARDED_ALLOW_IPS=130.176.0.0/18,15.158.0.0/16")
    error_message = "FORWARDED_ALLOW_IPS must be the sorted CloudFront ranges."
  }

  assert {
    condition     = !strcontains(aws_ssm_parameter.api_settings.value, "*")
    error_message = "The trusted proxies must never be *."
  }
}

run "api_settings_use_the_database_over_verified_tls_and_hold_no_secret" {
  command = apply

  assert {
    condition = alltrue([
      for line in [
        "CRAGMATCH_POSTGRES_HOST=db",
        "PGSSLMODE=verify-full",
        "PGSSLROOTCERT=/tls/server.crt",
        "CRAGMATCH_CORS_ORIGINS=https://${aws_cloudfront_distribution.web.domain_name}",
        "CRAGMATCH_CLAUDE_DAILY_CAP_USD=0.10",
        "CRAGMATCH_VOYAGE_DAILY_CAP_USD=0.05",
      ] : contains(split("\n", aws_ssm_parameter.api_settings.value), line)
    ])
    error_message = "The settings must name the database, verified TLS, the site as the only CORS origin and both caps."
  }

  assert {
    condition     = !strcontains(aws_ssm_parameter.api_settings.value, "localhost")
    error_message = "The cloud API must not allow localhost."
  }

  assert {
    condition = alltrue([
      for word in ["PASSWORD", "API_KEY", "sk-"] : !strcontains(aws_ssm_parameter.api_settings.value, word)
    ])
    error_message = "The settings are plain text and must hold no secret."
  }
}

run "api_settings_fit_a_standard_parameter" {
  command = apply

  override_data {
    target = data.aws_ec2_managed_prefix_list.cloudfront
    values = {
      id      = "pl-4fa04526"
      entries = [for i in range(60) : { cidr = "130.176.${i}.0/24", description = "mock" }]
    }
  }

  assert {
    condition = (
      aws_ssm_parameter.api_settings.type == "String"
      && aws_ssm_parameter.api_settings.tier == "Standard"
      && length(aws_ssm_parameter.api_settings.value) <= 4096
    )
    error_message = "60 ranges must still fit a Standard String parameter."
  }
}

run "api_key_slots_are_write_only_secure_strings" {
  command = apply

  assert {
    condition = (
      aws_ssm_parameter.anthropic_api_key.name == "/cragmatch/api/anthropic_api_key"
      && aws_ssm_parameter.voyage_api_key.name == "/cragmatch/api/voyage_api_key"
      && aws_ssm_parameter.anthropic_api_key.type == "SecureString"
      && aws_ssm_parameter.voyage_api_key.type == "SecureString"
      && aws_ssm_parameter.anthropic_api_key.value_wo_version == 1
      && aws_ssm_parameter.voyage_api_key.value_wo_version == 1
    )
    error_message = "Two SecureString slots, version 1."
  }

  assert {
    condition = (
      aws_ssm_parameter.anthropic_api_key.value_wo == null
      && aws_ssm_parameter.voyage_api_key.value_wo == null
    )
    error_message = "A write-only value must not be readable from the resource."
  }
}

run "daily_caps_cannot_be_negative" {
  command = plan

  variables {
    claude_daily_cap_usd = -1
  }

  expect_failures = [var.claude_daily_cap_usd]
}

run "host_can_pull_the_image_and_write_api_logs_only" {
  command = apply

  assert {
    condition = (
      jsondecode(aws_iam_role_policy.host_ecr_pull.policy).Statement[0].Action == "ecr:GetAuthorizationToken"
      && jsondecode(aws_iam_role_policy.host_ecr_pull.policy).Statement[0].Resource == "*"
      && jsondecode(aws_iam_role_policy.host_ecr_pull.policy).Statement[1].Action == [
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchCheckLayerAvailability",
      ]
      && jsondecode(aws_iam_role_policy.host_ecr_pull.policy).Statement[1].Resource == aws_ecr_repository.api.arn
      && length(jsondecode(aws_iam_role_policy.host_ecr_pull.policy).Statement) == 2
    )
    error_message = "The host may only log in to ECR and pull from the API repository."
  }

  assert {
    condition = (
      jsondecode(aws_iam_role_policy.host_api_logs.policy).Statement[0].Action == ["logs:CreateLogStream", "logs:PutLogEvents"]
      && jsondecode(aws_iam_role_policy.host_api_logs.policy).Statement[0].Resource == "${aws_cloudwatch_log_group.api.arn}:log-stream:*"
      && length(jsondecode(aws_iam_role_policy.host_api_logs.policy).Statement) == 1
    )
    error_message = "The host may only write streams in the API log group."
  }
}

run "api_logs_are_kept_two_weeks" {
  command = apply

  assert {
    condition     = aws_cloudwatch_log_group.api.name == "/cragmatch/api" && aws_cloudwatch_log_group.api.retention_in_days == 14
    error_message = "The log group is /cragmatch/api with 14 days of retention."
  }
}

run "deploy_role_pushes_one_repository_and_sends_one_document" {
  command = apply

  assert {
    condition = (
      length(jsondecode(aws_iam_role_policy.github_deploy_backend.policy).Statement) == 5
      && [for s in jsondecode(aws_iam_role_policy.github_deploy_backend.policy).Statement : s.Sid] == [
        "EcrLogin",
        "PushApiImage",
        "RunDeployDocument",
        "ReadCommandResult",
        "ReadDeployParameters",
      ]
    )
    error_message = "The deploy policy must have exactly the five planned statements."
  }

  assert {
    condition = (
      jsondecode(aws_iam_role_policy.github_deploy_backend.policy).Statement[1].Resource == aws_ecr_repository.api.arn
      && jsondecode(aws_iam_role_policy.github_deploy_backend.policy).Statement[2].Action == "ssm:SendCommand"
      && jsondecode(aws_iam_role_policy.github_deploy_backend.policy).Statement[2].Resource == [aws_instance.host.arn, aws_ssm_document.deploy_api.arn]
    )
    error_message = "Push to one repository only; SendCommand on the host and the deploy document only."
  }

  assert {
    condition = alltrue([
      for word in ["AWS-RunShellScript", "iam:", "\"Action\":\"*\""] :
      !strcontains(aws_iam_role_policy.github_deploy_backend.policy, word)
    ])
    error_message = "No generic shell document, no IAM actions, no wildcard action."
  }

  assert {
    condition = (
      jsondecode(aws_iam_role_policy.github_deploy_backend.policy).Statement[4].Action == "ssm:GetParameter"
      && jsondecode(aws_iam_role_policy.github_deploy_backend.policy).Statement[4].Resource == "arn:aws:ssm:eu-west-1:123456789012:parameter/cragmatch/deploy/*"
    )
    error_message = "Parameter reads are limited to /cragmatch/deploy/."
  }
}

run "deploy_document_runs_only_the_deploy_script_with_a_commit_sha" {
  command = apply

  assert {
    condition = (
      aws_ssm_document.deploy_api.name == "cragmatch-deploy-api"
      && aws_ssm_document.deploy_api.document_type == "Command"
      && jsondecode(aws_ssm_document.deploy_api.content).parameters.imageTag.allowedPattern == "^[0-9a-f]{40}$"
      && jsondecode(aws_ssm_document.deploy_api.content).parameters.runMigrations.allowedValues == ["yes", "no"]
      && jsondecode(aws_ssm_document.deploy_api.content).parameters.runMigrations.default == "yes"
    )
    error_message = "imageTag must be a 40-character SHA; runMigrations yes or no, default yes."
  }

  assert {
    condition = (
      length(jsondecode(aws_ssm_document.deploy_api.content).mainSteps) == 1
      && jsondecode(aws_ssm_document.deploy_api.content).mainSteps[0].inputs.runCommand == ["/opt/cragmatch/deploy-api.sh {{ imageTag }} {{ runMigrations }}"]
      && jsondecode(aws_ssm_document.deploy_api.content).mainSteps[0].inputs.timeoutSeconds == "900"
    )
    error_message = "One step that runs only the deploy script, with a 900 second timeout."
  }
}

run "deploy_parameters_name_the_host_and_the_api_url" {
  command = apply

  assert {
    condition = (
      aws_ssm_parameter.deploy_host_instance_id.name == "/cragmatch/deploy/host_instance_id"
      && aws_ssm_parameter.deploy_host_instance_id.value == aws_instance.host.id
      && aws_ssm_parameter.deploy_api_url.name == "/cragmatch/deploy/api_url"
      && aws_ssm_parameter.deploy_api_url.value == "https://${aws_cloudfront_distribution.api.domain_name}"
    )
    error_message = "The workflow reads the host id and the API URL from these parameters."
  }

  assert {
    condition     = output.api_url == aws_ssm_parameter.deploy_api_url.value && !endswith(output.api_url, "/")
    error_message = "The api_url output must equal the parameter and have no trailing slash."
  }
}

run "user_data_installs_one_api_unit_and_holds_no_secret" {
  command = apply

  assert {
    condition = alltrue([
      for pair in [
        ["/opt/cragmatch/cragmatch-api.service", file("host/cragmatch-api.service")],
        ["/opt/cragmatch/deploy-api.sh", file("host/deploy-api.sh")],
        ["/opt/cragmatch/render-api-environment.sh", file("host/render-api-environment.sh")],
        ["/opt/cragmatch/pull-api-image.sh", file("host/pull-api-image.sh")],
        ] : anytrue([
          for f in yamldecode(trimprefix(local.user_data, "#cloud-config\n")).write_files :
          f.path == pair[0] && f.content == pair[1]
      ])
    ])
    error_message = "The boot data must carry the exact API unit and the three scripts."
  }

  assert {
    condition = alltrue([
      for text in [
        "--name api",
        "-p 80:8000",
        "--network cragmatch",
        "--log-driver awslogs",
        "RequiresMountsFor=/srv/cragmatch",
        "ConditionPathExists=/srv/cragmatch/api/current-image",
      ] : strcontains(one([for f in yamldecode(trimprefix(local.user_data, "#cloud-config\n")).write_files : f.content if f.path == "/opt/cragmatch/cragmatch-api.service"]), text)
    ])
    error_message = "The unit must run one container named api on the Docker network, with CloudWatch logs and the data volume."
  }

  assert {
    condition = anytrue([
      for line in split("\n", one([for f in yamldecode(trimprefix(local.user_data, "#cloud-config\n")).write_files : f.content if f.path == "/opt/cragmatch/cragmatch-api.service"])) :
      startswith(line, "ExecStart=") && endswith(line, "$${API_IMAGE}")
    ])
    error_message = "Nothing may follow the image in ExecStart, so the image's own command (one worker) applies."
  }

  assert {
    # The scripts legitimately contain "API_KEY=%s" and "POSTGRES_PASSWORD=%s"; what must never
    # appear is a value assigned to them.
    condition = (
      !can(regex("POSTGRES_PASSWORD=[A-Za-z0-9]", local.user_data))
      && !can(regex("API_KEY=[A-Za-z0-9]", local.user_data))
      && !strcontains(local.user_data, "sk-ant")
    )
    error_message = "The boot data must not assign a literal secret."
  }

  assert {
    condition     = length(aws_instance.host.user_data_base64) < 16384
    error_message = "EC2 user data is limited to 16384 bytes."
  }
}
