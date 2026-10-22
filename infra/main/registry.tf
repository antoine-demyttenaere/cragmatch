resource "aws_ecr_repository" "api" {
  name = "cragmatch-api"

  # A tag is the full commit SHA, so it must always mean the same image (rollbacks rely on it).
  image_tag_mutability = "IMMUTABLE"

  # Every image can be rebuilt from git, and destroy must not get stuck on a non-empty repository.
  force_delete = true

  # Basic scan is free.
  image_scanning_configuration {
    scan_on_push = true
  }
}

# Five tags give four steps of rollback for about 0.10 USD per GB-month at most.
resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Untagged images expire after a day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep the newest 5 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 5
        }
        action = { type = "expire" }
      },
    ]
  })
}
