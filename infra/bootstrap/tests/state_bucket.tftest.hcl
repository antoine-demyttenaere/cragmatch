mock_provider "aws" {
  override_data {
    target = data.aws_caller_identity.current
    values = {
      account_id = "123456789012"
    }
  }
}

variables {
  region         = "eu-west-1"
  aws_account_id = "123456789012"
}

run "state_bucket_is_named_after_the_account_and_region" {
  command = apply

  assert {
    condition     = aws_s3_bucket.state.bucket == "cragmatch-tfstate-123456789012-eu-west-1"
    error_message = "The bucket name must hold the account id and the region."
  }
}

run "versioning_is_enabled" {
  command = apply

  assert {
    condition     = aws_s3_bucket_versioning.state.versioning_configuration[0].status == "Enabled"
    error_message = "Versioning must be Enabled."
  }
}

run "bucket_is_private_encrypted_and_tls_only" {
  command = apply

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.state.block_public_acls,
      aws_s3_bucket_public_access_block.state.block_public_policy,
      aws_s3_bucket_public_access_block.state.ignore_public_acls,
      aws_s3_bucket_public_access_block.state.restrict_public_buckets,
    ])
    error_message = "All four public access flags must be true."
  }

  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.state.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "The bucket must use AES256 encryption."
  }

  assert {
    condition = anytrue([
      for s in jsondecode(aws_s3_bucket_policy.state.policy).Statement :
      s.Effect == "Deny" && s.Condition.Bool["aws:SecureTransport"] == "false"
    ])
    error_message = "The bucket policy must deny requests without TLS."
  }
}

run "old_state_versions_expire" {
  command = apply

  assert {
    condition     = one(aws_s3_bucket_lifecycle_configuration.state.rule).noncurrent_version_expiration[0].noncurrent_days == 90
    error_message = "Noncurrent versions must expire after 90 days."
  }

  assert {
    condition     = one(aws_s3_bucket_lifecycle_configuration.state.rule).abort_incomplete_multipart_upload[0].days_after_initiation == 7
    error_message = "Incomplete multipart uploads must be aborted after 7 days."
  }
}

run "bucket_survives_destroy_by_default" {
  command = apply

  assert {
    condition     = aws_s3_bucket.state.force_destroy == false
    error_message = "force_destroy must be false by default."
  }
}

run "bucket_can_be_emptied_when_allowed" {
  command = apply

  variables {
    allow_destroy = true
  }

  assert {
    condition     = aws_s3_bucket.state.force_destroy == true
    error_message = "allow_destroy = true must set force_destroy."
  }
}

run "account_id_must_be_twelve_digits" {
  command = plan

  variables {
    aws_account_id = "12345"
  }

  expect_failures = [var.aws_account_id]
}

run "backend_config_output_points_at_the_bucket" {
  command = apply

  assert {
    condition     = output.backend_config == "bucket = \"cragmatch-tfstate-123456789012-eu-west-1\"\nregion = \"eu-west-1\"\n"
    error_message = "The backend_config output must name the bucket and the region."
  }
}
