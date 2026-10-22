mock_provider "aws" {
  # The provider checks that these attributes look like ARNs, so the generated strings are not enough.
  mock_resource "aws_iam_role" {
    defaults = {
      arn = "arn:aws:iam::123456789012:role/mock"
    }
  }

  mock_resource "aws_s3_bucket" {
    defaults = {
      arn = "arn:aws:s3:::cragmatch-web-123456789012-eu-west-1"
    }
  }

  mock_resource "aws_cloudfront_distribution" {
    defaults = {
      arn = "arn:aws:cloudfront::123456789012:distribution/EMOCKDISTRIBUTION"
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

  # The cache policy data source is not overridden: a mock cannot set its id (the provider reads it
  # from the lookup), so the test checks its name and that the behaviour uses it.
}

# The mock gives every distribution the same ARN. The API's gets its own, so a policy that pointed at
# the wrong distribution could not pass the comparisons below.
override_resource {
  target = aws_cloudfront_distribution.api
  values = {
    arn = "arn:aws:cloudfront::123456789012:distribution/EMOCKAPI"
  }
}

variables {
  region            = "eu-west-1"
  aws_account_id    = "123456789012"
  owner_email       = "owner@example.com"
  github_repository = "someone/cragmatch"
}

run "site_bucket_is_private_and_encrypted" {
  command = apply

  assert {
    condition     = aws_s3_bucket.web.bucket == "cragmatch-web-123456789012-eu-west-1" && aws_s3_bucket.web.force_destroy == true
    error_message = "The bucket must be cragmatch-web-<account>-<region> and destroyable with its files."
  }

  assert {
    condition = (
      aws_s3_bucket_public_access_block.web.block_public_acls == true
      && aws_s3_bucket_public_access_block.web.block_public_policy == true
      && aws_s3_bucket_public_access_block.web.ignore_public_acls == true
      && aws_s3_bucket_public_access_block.web.restrict_public_buckets == true
    )
    error_message = "All four public access flags must be on."
  }

  assert {
    condition = (
      one(aws_s3_bucket_ownership_controls.web.rule).object_ownership == "BucketOwnerEnforced"
      && one(one(aws_s3_bucket_server_side_encryption_configuration.web.rule).apply_server_side_encryption_by_default).sse_algorithm == "AES256"
    )
    error_message = "Owner enforced and SSE-S3 encryption."
  }
}

run "only_the_web_distribution_reads_only_the_site_files" {
  command = apply

  assert {
    condition = (
      length(jsondecode(aws_s3_bucket_policy.web.policy).Statement) == 2
      && jsondecode(aws_s3_bucket_policy.web.policy).Statement[0].Effect == "Allow"
      && jsondecode(aws_s3_bucket_policy.web.policy).Statement[0].Principal == { Service = "cloudfront.amazonaws.com" }
      && jsondecode(aws_s3_bucket_policy.web.policy).Statement[0].Action == "s3:GetObject"
      && jsondecode(aws_s3_bucket_policy.web.policy).Statement[0].Resource == [
        "${aws_s3_bucket.web.arn}/index.html",
        "${aws_s3_bucket.web.arn}/assets/*",
      ]
    )
    error_message = "Only CloudFront may GetObject, and only index.html and assets/*."
  }

  assert {
    condition = (
      jsondecode(aws_s3_bucket_policy.web.policy).Statement[0].Condition.StringEquals["AWS:SourceArn"] == aws_cloudfront_distribution.web.arn
      && aws_cloudfront_distribution.web.arn != aws_cloudfront_distribution.api.arn
    )
    error_message = "The read must be limited to the web distribution's ARN, which differs from the API's."
  }

  assert {
    condition = (
      jsondecode(aws_s3_bucket_policy.web.policy).Statement[1].Effect == "Deny"
      && jsondecode(aws_s3_bucket_policy.web.policy).Statement[1].Action == "s3:*"
      && jsondecode(aws_s3_bucket_policy.web.policy).Statement[1].Condition.Bool["aws:SecureTransport"] == "false"
    )
    error_message = "A Deny for plain HTTP must exist."
  }
}

run "web_distribution_serves_the_bucket_over_https_only" {
  command = apply

  assert {
    condition = (
      length(aws_cloudfront_distribution.web.origin) == 1
      && one(aws_cloudfront_distribution.web.origin).domain_name == aws_s3_bucket.web.bucket_regional_domain_name
      && one(aws_cloudfront_distribution.web.origin).origin_access_control_id == aws_cloudfront_origin_access_control.web.id
      && aws_cloudfront_origin_access_control.web.origin_access_control_origin_type == "s3"
      && aws_cloudfront_origin_access_control.web.signing_behavior == "always"
      && aws_cloudfront_origin_access_control.web.signing_protocol == "sigv4"
    )
    error_message = "One origin: the bucket's regional domain through the origin access control."
  }

  assert {
    condition = (
      aws_cloudfront_distribution.web.default_root_object == "index.html"
      && one(aws_cloudfront_distribution.web.default_cache_behavior).allowed_methods == toset(["GET", "HEAD"])
      && one(aws_cloudfront_distribution.web.default_cache_behavior).compress == true
      && one(aws_cloudfront_distribution.web.default_cache_behavior).viewer_protocol_policy == "redirect-to-https"
      && data.aws_cloudfront_cache_policy.caching_optimized.name == "Managed-CachingOptimized"
      && one(aws_cloudfront_distribution.web.default_cache_behavior).cache_policy_id == data.aws_cloudfront_cache_policy.caching_optimized.id
      && one(aws_cloudfront_distribution.web.default_cache_behavior).response_headers_policy_id == aws_cloudfront_response_headers_policy.web.id
    )
    error_message = "index.html root, GET and HEAD, compressed, HTTPS redirect, CachingOptimized and our headers policy."
  }

  assert {
    condition = (
      one(aws_cloudfront_distribution.web.viewer_certificate).cloudfront_default_certificate == true
      && try(length(aws_cloudfront_distribution.web.aliases), 0) == 0
      && aws_cloudfront_distribution.web.price_class == "PriceClass_100"
    )
    error_message = "Default certificate, no aliases, PriceClass_100."
  }
}

run "unknown_paths_open_the_app" {
  command = apply

  assert {
    condition = (
      length(aws_cloudfront_distribution.web.custom_error_response) == 2
      && toset([for e in aws_cloudfront_distribution.web.custom_error_response : e.error_code]) == toset([403, 404])
      && alltrue([
        for e in aws_cloudfront_distribution.web.custom_error_response :
        e.response_page_path == "/index.html" && e.response_code == 200 && e.error_caching_min_ttl == 0
      ])
    )
    error_message = "403 and 404 must both answer 200 with /index.html and no error caching."
  }
}

run "security_headers_pin_https_and_the_api" {
  command = apply

  assert {
    condition = (
      one(one(aws_cloudfront_response_headers_policy.web.security_headers_config).strict_transport_security).access_control_max_age_sec == 31536000
      && one(one(aws_cloudfront_response_headers_policy.web.security_headers_config).strict_transport_security).override == true
      && one(one(aws_cloudfront_response_headers_policy.web.security_headers_config).content_type_options).override == true
      && one(one(aws_cloudfront_response_headers_policy.web.security_headers_config).frame_options).frame_option == "DENY"
      && one(one(aws_cloudfront_response_headers_policy.web.security_headers_config).frame_options).override == true
      && one(one(aws_cloudfront_response_headers_policy.web.security_headers_config).referrer_policy).referrer_policy == "no-referrer"
      && one(one(aws_cloudfront_response_headers_policy.web.security_headers_config).referrer_policy).override == true
    )
    error_message = "HSTS for a year, nosniff, DENY and no-referrer, all overriding the origin."
  }

  assert {
    condition = (
      strcontains(one(one(aws_cloudfront_response_headers_policy.web.security_headers_config).content_security_policy).content_security_policy, "script-src 'self'")
      && strcontains(one(one(aws_cloudfront_response_headers_policy.web.security_headers_config).content_security_policy).content_security_policy, "frame-ancestors 'none'")
      && strcontains(one(one(aws_cloudfront_response_headers_policy.web.security_headers_config).content_security_policy).content_security_policy, "connect-src 'self' https://${aws_cloudfront_distribution.api.domain_name}")
      && one(one(aws_cloudfront_response_headers_policy.web.security_headers_config).content_security_policy).override == true
    )
    error_message = "The CSP must allow scripts from self only, no framing, and connections to self and the API."
  }

  assert {
    condition = alltrue([
      for word in ["unsafe-inline", "*"] :
      !strcontains(one(one(aws_cloudfront_response_headers_policy.web.security_headers_config).content_security_policy).content_security_policy, word)
    ])
    error_message = "The CSP must contain neither unsafe-inline nor a wildcard."
  }
}

run "deploy_role_publishes_the_site_and_invalidates_it_only" {
  command = apply

  assert {
    condition = (
      length(jsondecode(aws_iam_role_policy.github_deploy_web.policy).Statement) == 4
      && [for s in jsondecode(aws_iam_role_policy.github_deploy_web.policy).Statement : s.Sid] == [
        "ListSite",
        "WriteSite",
        "ReadRelease",
        "InvalidateSite",
      ]
    )
    error_message = "The web deploy policy must have exactly the four planned statements."
  }

  assert {
    condition = (
      jsondecode(aws_iam_role_policy.github_deploy_web.policy).Statement[0].Action == "s3:ListBucket"
      && jsondecode(aws_iam_role_policy.github_deploy_web.policy).Statement[0].Resource == aws_s3_bucket.web.arn
      && jsondecode(aws_iam_role_policy.github_deploy_web.policy).Statement[1].Action == ["s3:PutObject", "s3:DeleteObject"]
      && jsondecode(aws_iam_role_policy.github_deploy_web.policy).Statement[1].Resource == "${aws_s3_bucket.web.arn}/*"
      && jsondecode(aws_iam_role_policy.github_deploy_web.policy).Statement[2].Action == "s3:GetObject"
      && jsondecode(aws_iam_role_policy.github_deploy_web.policy).Statement[2].Resource == "${aws_s3_bucket.web.arn}/release/*"
      && jsondecode(aws_iam_role_policy.github_deploy_web.policy).Statement[3].Action == ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation"]
      && jsondecode(aws_iam_role_policy.github_deploy_web.policy).Statement[3].Resource == aws_cloudfront_distribution.web.arn
      && aws_cloudfront_distribution.web.arn != aws_cloudfront_distribution.api.arn
    )
    error_message = "List, write, read releases, and invalidate the web distribution only."
  }

  assert {
    condition = alltrue([
      for word in ["iam:", "\"Action\":\"*\"", "\"Resource\":\"*\""] :
      !strcontains(aws_iam_role_policy.github_deploy_web.policy, word)
    ])
    error_message = "No IAM actions and no wildcard action or resource."
  }
}

run "deploy_parameters_name_the_site" {
  command = apply

  assert {
    condition = (
      aws_ssm_parameter.deploy_web_bucket.name == "/cragmatch/deploy/web_bucket"
      && aws_ssm_parameter.deploy_web_bucket.value == aws_s3_bucket.web.id
      && aws_ssm_parameter.deploy_web_distribution_id.name == "/cragmatch/deploy/web_distribution_id"
      && aws_ssm_parameter.deploy_web_distribution_id.value == aws_cloudfront_distribution.web.id
      && aws_ssm_parameter.deploy_web_url.name == "/cragmatch/deploy/web_url"
      && aws_ssm_parameter.deploy_web_url.value == "https://${aws_cloudfront_distribution.web.domain_name}"
    )
    error_message = "The workflow reads the bucket, the distribution id and the site URL from these parameters."
  }

  assert {
    condition     = output.web_url == aws_ssm_parameter.deploy_web_url.value && !endswith(output.web_url, "/")
    error_message = "The web_url output must equal the parameter and have no trailing slash."
  }
}

run "web_hosting_adds_no_paid_extras" {
  command = apply

  assert {
    condition     = try(length(aws_cloudfront_distribution.web.logging_config), 0) == 0 && try(length(aws_cloudfront_distribution.web.aliases), 0) == 0
    error_message = "No logging and no custom domain."
  }

  # A test cannot list the state, so this reads the stack's own files.
  assert {
    condition = length(aws_cloudfront_distribution.web.origin) == 1 && alltrue([
      for f in fileset(".", "*.tf") :
      !can(regex("resource \"(aws_cloudfront_function|aws_acm_certificate|aws_wafv2_web_acl)\"", file(f)))
    ])
    error_message = "The site must add no CloudFront function, certificate or web ACL."
  }
}
