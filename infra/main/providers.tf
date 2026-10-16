provider "aws" {
  region = var.region

  # Credentials from the laptop may belong to another account; refuse to plan against it.
  allowed_account_ids = [var.aws_account_id]

  # The Project tag is what the billing view and the tflint tag rule group by (cost of CragMatch).
  default_tags {
    tags = {
      Project   = "cragmatch"
      ManagedBy = "terraform"
      Stack     = "main"
    }
  }
}

provider "random" {}
