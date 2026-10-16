plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

plugin "aws" {
  enabled = true
  version = "0.49.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

# Every taggable resource must carry the Project tag (it can come from the provider's default_tags).
rule "aws_resource_missing_tags" {
  enabled = true
  tags    = ["Project"]
}
