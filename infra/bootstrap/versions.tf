terraform {
  required_version = ">= 1.11.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.68"
    }
  }

  # The backend is partial on purpose: the bucket name holds the account id, which is never
  # committed. The bucket and region come from -backend-config=../backend.hcl (written by the
  # runbook from this stack's output). The very first run has no bucket yet, so it uses a local
  # backend_override.tf and then migrates the state into the bucket (see infra/RUNBOOK.md).
  backend "s3" {
    key          = "bootstrap/terraform.tfstate"
    use_lockfile = true
    encrypt      = true
  }
}
