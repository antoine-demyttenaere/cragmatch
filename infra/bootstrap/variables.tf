variable "region" {
  description = "AWS region for the state bucket. Europe only: see the region reasons in infra/RUNBOOK.md."
  type        = string
  default     = "eu-west-1"

  validation {
    condition     = startswith(var.region, "eu-")
    error_message = "The region must be a European region (it starts with eu-)."
  }
}

variable "aws_account_id" {
  description = "The 12-digit id of the CragMatch AWS account. Never committed; set it in terraform.tfvars."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be exactly 12 digits."
  }
}

variable "allow_destroy" {
  description = "Set to true only to tear the project down: it lets Terraform empty and delete the state bucket."
  type        = bool
  default     = false
}
