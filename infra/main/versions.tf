terraform {
  required_version = ">= 1.11.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.68"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }

  # Partial backend, same reason as in infra/bootstrap: the bucket name holds the account id.
  # Use: terraform init -backend-config=../backend.hcl
  backend "s3" {
    key          = "main/terraform.tfstate"
    use_lockfile = true
    encrypt      = true
  }
}
