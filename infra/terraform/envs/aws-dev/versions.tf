terraform {
  required_version = ">= 1.10.0"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 6.70" }
    random = { source = "hashicorp/random", version = "~> 3.9" }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = merge({
      Project     = "euron-open-gpuwatch"
      Environment = var.environment
      ManagedBy   = "terraform"
    }, var.extra_tags)
  }
}
