variable "region" {
  description = "AWS region for everything in this stack. Europe only: see the region reasons in infra/RUNBOOK.md."
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

variable "owner_email" {
  description = "Email address that receives the budget alerts. Never committed; set it in terraform.tfvars."
  type        = string

  validation {
    condition     = can(regex("^[^@ ]+@[^@ ]+[.][^@ ]+$", var.owner_email))
    error_message = "owner_email must look like an email address."
  }
}

variable "github_repository" {
  description = "The GitHub repository allowed to deploy, as owner/name."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must look like owner/name."
  }
}

variable "instance_type" {
  description = "EC2 instance type of the host. Graviton only: the cloud database image is built for arm64 here, and t4g is the cheapest family."
  type        = string
  default     = "t4g.small"

  validation {
    condition     = startswith(var.instance_type, "t4g.")
    error_message = "instance_type must be a t4g type (arm64)."
  }
}

variable "data_volume_gb" {
  description = "Size in GiB of the encrypted EBS volume that holds the Postgres data."
  type        = number
  default     = 4

  validation {
    condition     = var.data_volume_gb >= 1 && var.data_volume_gb <= 50
    error_message = "data_volume_gb must be between 1 and 50."
  }
}

variable "backup_retention_days" {
  description = "How many daily snapshots of the data volume are kept."
  type        = number
  default     = 7

  validation {
    condition     = var.backup_retention_days >= 3 && var.backup_retention_days <= 35
    error_message = "backup_retention_days must be between 3 and 35."
  }
}

variable "budget_limit_usd" {
  description = "Monthly budget in USD. AWS bills in USD; 11.20 is about 10 EUR at the ECB rate of 2026-10-13 (1 EUR = 1.1188 USD)."
  type        = number
  default     = 11.20
}

variable "budget_alert_percent" {
  description = "Percentage of the budget at which the first (actual spend) alert fires. 50 percent is about 5 EUR."
  type        = number
  default     = 50
}

variable "activate_cost_allocation_tag" {
  description = "Set to true the day after the first apply, once the Project tag key is known to billing, so the billing view can group by it."
  type        = bool
  default     = false
}

# These defaults match app/core/config.py. Set a higher cloud cap in terraform.tfvars. 0 switches that provider off.
variable "claude_daily_cap_usd" {
  description = "Daily spending cap for Claude in USD (ticket 022). 0 switches Claude off."
  type        = number
  default     = 0.10

  validation {
    condition     = var.claude_daily_cap_usd >= 0
    error_message = "claude_daily_cap_usd cannot be negative."
  }
}

variable "voyage_daily_cap_usd" {
  description = "Daily spending cap for Voyage in USD (ticket 022). 0 switches Voyage off."
  type        = number
  default     = 0.05

  validation {
    condition     = var.voyage_daily_cap_usd >= 0
    error_message = "voyage_daily_cap_usd cannot be negative."
  }
}

variable "db_password_version" {
  description = "Bumping this writes a NEW password value to the SSM parameter but does not change the password inside Postgres. Follow the rotation steps in infra/RUNBOOK.md, which do both."
  type        = number
  default     = 1
}
