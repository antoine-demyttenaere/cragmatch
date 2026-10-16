# Special characters are off because the value goes into URLs and environment files unescaped.
ephemeral "random_password" "db" {
  length  = 32
  special = false
}

# Write-only: the value is in neither the plan nor the state. The host reads it at boot by name.
resource "aws_ssm_parameter" "db_password" {
  name             = "/cragmatch/db/password"
  type             = "SecureString"
  value_wo         = ephemeral.random_password.db.result
  value_wo_version = var.db_password_version
}

resource "aws_ebs_volume" "data" {
  availability_zone = aws_subnet.public.availability_zone
  type              = "gp3"
  size              = var.data_volume_gb
  encrypted         = true

  tags = {
    Name   = "cragmatch-db-data"
    Backup = "cragmatch-daily"
  }
}

# The snapshots are crash-consistent. Postgres recovers from one like from a power cut, because
# data and WAL are on this one volume.
resource "aws_dlm_lifecycle_policy" "db" {
  description        = "Daily snapshots of the CragMatch data volume"
  execution_role_arn = aws_iam_role.dlm.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["VOLUME"]
    target_tags    = { Backup = "cragmatch-daily" }

    schedule {
      name      = "daily"
      copy_tags = true

      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = ["03:00"]
      }

      retain_rule {
        count = var.backup_retention_days
      }

      tags_to_add = { SnapshotOf = "cragmatch-db-data" }
    }
  }
}
