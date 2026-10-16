data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

locals {
  # The host files exist once, under host/, and are written onto the host by cloud-init.
  # Only the parameter NAME of the password is here, never a secret.
  user_data = "#cloud-config\n${yamlencode({
    write_files = [
      {
        path        = "/opt/cragmatch/host-settings"
        permissions = "0644"
        content = join("\n", [
          "REGION=${var.region}",
          "DATA_VOLUME_ID=${aws_ebs_volume.data.id}",
          "DB_PASSWORD_PARAMETER=${aws_ssm_parameter.db_password.name}",
          "",
        ])
      },
      {
        path        = "/opt/cragmatch/host-setup.sh"
        permissions = "0755"
        content     = file("${path.module}/host/host-setup.sh")
      },
      {
        path        = "/opt/cragmatch/cragmatch-db.service"
        permissions = "0644"
        content     = file("${path.module}/host/cragmatch-db.service")
      },
      {
        path        = "/opt/cragmatch/db/Dockerfile"
        permissions = "0644"
        content     = file("${path.module}/host/db/Dockerfile")
      },
      {
        path        = "/opt/cragmatch/db/initdb/10-extensions.sql"
        permissions = "0644"
        content     = file("${path.module}/host/db/initdb/10-extensions.sql")
      },
      {
        path        = "/opt/cragmatch/db/initdb/20-tls-only.sh"
        permissions = "0644"
        content     = file("${path.module}/host/db/initdb/20-tls-only.sh")
      },
    ]
    runcmd = [["bash", "/opt/cragmatch/host-setup.sh"]]
  })}"
}

resource "aws_instance" "host" {
  # AL2023 arm64. The image is pinned by ignore_changes below, so it is read once.
  ami           = data.aws_ssm_parameter.al2023_arm64.insecure_value
  instance_type = var.instance_type

  # Provider 6 deprecates the network_interface block in favour of this one.
  primary_network_interface {
    network_interface_id = aws_network_interface.host.id
  }

  iam_instance_profile = aws_iam_instance_profile.host.name

  # The T4g free trial bills surplus CPU credits, so the host never goes into unlimited mode.
  credit_specification {
    cpu_credits = "standard"
  }

  # Hop limit 1: containers cannot borrow the host's role. Ticket 025 passes secrets in from the host.
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = 12
    encrypted   = true

    tags = { Name = "cragmatch-host-root" }
  }

  user_data                   = local.user_data
  user_data_replace_on_change = true

  tags = { Name = "cragmatch-host" }

  # The boot script reads this parameter.
  depends_on = [aws_ssm_parameter.db_password, aws_iam_role_policy.host_parameters]

  lifecycle {
    # A newer AL2023 image would otherwise replace the host on any apply. Updating the OS is
    # deliberate: terraform apply -replace=aws_instance.host (see infra/RUNBOOK.md).
    ignore_changes = [ami]
  }
}

# Stopping first lets Postgres shut down cleanly before the disk goes away during a replacement.
resource "aws_volume_attachment" "data" {
  device_name                    = "/dev/sdf"
  volume_id                      = aws_ebs_volume.data.id
  instance_id                    = aws_instance.host.id
  stop_instance_before_detaching = true
}
