provider "aws" {
  region = var.region

  # Credentials from the laptop may belong to another account; refuse to plan against it.
  allowed_account_ids = [var.aws_account_id]

  # This tag is what the billing view and the tflint tag rule group by.
  default_tags {
    tags = {
      Project   = "cragmatch"
      ManagedBy = "terraform"
      Stack     = "bootstrap"
    }
  }
}
