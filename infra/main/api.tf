data "aws_ec2_managed_prefix_list" "cloudfront" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

# The only inbound rule of the host. The list weighs about 55 of the 60 rules a security group
# allows, so nothing else fits here.
resource "aws_vpc_security_group_ingress_rule" "cloudfront_http" {
  security_group_id = aws_security_group.host.id
  description       = "HTTP from CloudFront only (the API distribution)"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  prefix_list_id    = data.aws_ec2_managed_prefix_list.cloudfront.id
}

locals {
  api_settings = {
    CRAGMATCH_POSTGRES_USER = "cragmatch"
    CRAGMATCH_POSTGRES_DB   = "cragmatch"
    CRAGMATCH_POSTGRES_HOST = "db"
    CRAGMATCH_POSTGRES_PORT = "5432"

    # libpq reads these two. verify-full checks the certificate and the name db (024's self-signed
    # certificate, mounted read-only into the container).
    PGSSLMODE     = "verify-full"
    PGSSLROOTCERT = "/tls/server.crt"

    # uvicorn trusts X-Forwarded-For only from these addresses (CloudFront's) and walks the header
    # from the right, so it takes the viewer address CloudFront appended. NEVER set this to *: uvicorn
    # then takes the LEFTMOST entry, which the viewer controls, and every forged header would get its
    # own rate-limit bucket.
    FORWARDED_ALLOW_IPS = join(",", sort([for e in data.aws_ec2_managed_prefix_list.cloudfront.entries : e.cidr]))

    CRAGMATCH_CORS_ORIGINS = var.cors_origins

    CRAGMATCH_CLAUDE_DAILY_CAP_USD = format("%.2f", var.claude_daily_cap_usd)
    CRAGMATCH_VOYAGE_DAILY_CAP_USD = format("%.2f", var.voyage_daily_cap_usd)
  }

  # The database password and the two API keys are deliberately not here: this parameter is plain
  # text. The host adds them from their own SecureString parameters. Map keys are sorted, so the
  # text is deterministic.
  api_settings_text = join("\n", [for k, v in local.api_settings : "${k}=${v}"])
}

resource "aws_ssm_parameter" "api_settings" {
  name  = "/cragmatch/api/settings"
  type  = "String"
  tier  = "Standard"
  value = local.api_settings_text

  lifecycle {
    precondition {
      condition     = length(local.api_settings_text) <= 4096
      error_message = "The API settings no longer fit a Standard parameter (4096 characters). Use the Advanced tier or shorten them."
    }
  }
}

# Empty slots. The user types the real keys in the console. Write-only keeps both the placeholder and
# the real key out of the plan and the state. Never bump value_wo_version: that would write "unset"
# over the real key.
resource "aws_ssm_parameter" "anthropic_api_key" {
  name             = "/cragmatch/api/anthropic_api_key"
  type             = "SecureString"
  value_wo         = "unset"
  value_wo_version = 1
}

resource "aws_ssm_parameter" "voyage_api_key" {
  name             = "/cragmatch/api/voyage_api_key"
  type             = "SecureString"
  value_wo         = "unset"
  value_wo_version = 1
}

# Docker's awslogs driver on the host writes here. 14 days stays inside the 5 GB free allowance.
resource "aws_cloudwatch_log_group" "api" {
  name              = "/cragmatch/api"
  retention_in_days = 14
}

# Separate inline policies, so "host_role_reads_only_cragmatch_parameters" stays true.
resource "aws_iam_role_policy" "host_ecr_pull" {
  name = "cragmatch-host-ecr-pull"
  role = aws_iam_role.host.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability",
        ]
        Resource = aws_ecr_repository.api.arn
      },
    ]
  })
}

resource "aws_iam_role_policy" "host_api_logs" {
  name = "cragmatch-host-api-logs"
  role = aws_iam_role.host.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
      ]
      # The provider's arn has no trailing :*, so the streams are named explicitly.
      Resource = "${aws_cloudwatch_log_group.api.arn}:log-stream:*"
    }]
  })
}

# Read by the Deploy workflow. Both change by themselves when the host is replaced.
resource "aws_ssm_parameter" "deploy_host_instance_id" {
  name  = "/cragmatch/deploy/host_instance_id"
  type  = "String"
  value = aws_instance.host.id
}

resource "aws_ssm_parameter" "deploy_api_url" {
  name  = "/cragmatch/deploy/api_url"
  type  = "String"
  value = "https://${aws_cloudfront_distribution.api.domain_name}"
}
