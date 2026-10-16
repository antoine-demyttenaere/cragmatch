data "aws_caller_identity" "current" {}

# Policies use jsonencode(), not aws_iam_policy_document, so the offline tests can decode them.

resource "aws_iam_role" "host" {
  name = "cragmatch-host"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Session Manager: the only way into the host (no SSH, no key pair).
resource "aws_iam_role_policy_attachment" "host_ssm" {
  role       = aws_iam_role.host.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# The AWS-managed aws/ssm key needs no KMS statement for SecureString reads.
resource "aws_iam_role_policy" "host_parameters" {
  name = "read-cragmatch-parameters"
  role = aws_iam_role.host.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ssm:GetParameter",
        "ssm:GetParameters",
      ]
      Resource = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/cragmatch/*"
    }]
  })
}

resource "aws_iam_instance_profile" "host" {
  name = "cragmatch-host"
  role = aws_iam_role.host.name
}

resource "aws_iam_role" "dlm" {
  name = "cragmatch-dlm"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "dlm.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "dlm" {
  role       = aws_iam_role.dlm.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

# No thumbprint: IAM validates GitHub's certificate with its own trusted CAs.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# Exact match (StringEquals, not StringLike) on one repository and one branch. The branch is used
# instead of a GitHub environment because environments on private repositories need a paid plan.
# The role has no permissions yet: ticket 025 adds ECR push and SSM Run Command on the host,
# ticket 026 adds the S3 sync and the CloudFront invalidation.
resource "aws_iam_role" "github_deploy" {
  name                 = "cragmatch-github-deploy"
  max_session_duration = 3600

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repository}:ref:refs/heads/main"
        }
      }
    }]
  })
}
