resource "aws_budgets_budget" "monthly" {
  name         = "cragmatch-monthly"
  budget_type  = "COST"
  time_unit    = "MONTHLY"
  limit_amount = tostring(var.budget_limit_usd)
  limit_unit   = "USD"

  # Credits are left out of the count, so they cannot hide the real spend.
  cost_types {
    include_credit = false
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = var.budget_alert_percent
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.owner_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.owner_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.owner_email]
  }
}

# Billing only learns a tag key up to 24 hours after first use, so this is switched on the next day.
resource "aws_ce_cost_allocation_tag" "project" {
  count = var.activate_cost_allocation_tag ? 1 : 0

  tag_key = "Project"
  status  = "Active"
}
