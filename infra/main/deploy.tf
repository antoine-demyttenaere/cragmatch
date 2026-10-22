# The only thing the GitHub role can run on the host: one script, with a commit SHA. A generic
# AWS-RunShellScript would let the role run any command as root.
resource "aws_ssm_document" "deploy_api" {
  name            = "cragmatch-deploy-api"
  document_type   = "Command"
  document_format = "JSON"

  content = jsonencode({
    schemaVersion = "2.2"
    description   = "Deploy a CragMatch API image (pull, migrate, restart, check health)"
    parameters = {
      imageTag = {
        type           = "String"
        description    = "Full 40-character commit SHA of an image already in ECR"
        allowedPattern = "^[0-9a-f]{40}$"
      }
      runMigrations = {
        type          = "String"
        description   = "yes applies Alembic migrations first; no for a rollback (an older image does not know a newer revision)"
        allowedValues = ["yes", "no"]
        default       = "yes"
      }
    }
    mainSteps = [{
      action = "aws:runShellScript"
      name   = "deployApi"
      inputs = {
        timeoutSeconds = "900"
        runCommand     = ["/opt/cragmatch/deploy-api.sh {{ imageTag }} {{ runMigrations }}"]
      }
    }]
  })
}

# Ticket 026 adds its own separate inline policy (S3 and the CloudFront invalidation).
resource "aws_iam_role_policy" "github_deploy_backend" {
  name = "cragmatch-deploy-backend"
  role = aws_iam_role.github_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EcrLogin"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "PushApiImage"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:CompleteLayerUpload",
          "ecr:DescribeImages",
          "ecr:GetDownloadUrlForLayer",
          "ecr:InitiateLayerUpload",
          "ecr:PutImage",
          "ecr:UploadLayerPart",
        ]
        Resource = aws_ecr_repository.api.arn
      },
      {
        Sid      = "RunDeployDocument"
        Effect   = "Allow"
        Action   = "ssm:SendCommand"
        Resource = [aws_instance.host.arn, aws_ssm_document.deploy_api.arn]
      },
      {
        # This action supports no resource-level restriction.
        Sid      = "ReadCommandResult"
        Effect   = "Allow"
        Action   = "ssm:GetCommandInvocation"
        Resource = "*"
      },
      {
        Sid      = "ReadDeployParameters"
        Effect   = "Allow"
        Action   = "ssm:GetParameter"
        Resource = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/cragmatch/deploy/*"
      },
    ]
  })
}
