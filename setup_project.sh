#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(pwd)"

echo "Tworzenie struktury projektu w:"
echo "$PROJECT_ROOT"
echo

directories=(
  "src"
  "tests"
  "data/raw"
  "data/processed"
)

files=(
  "src/__init__.py"
  "src/extract.py"
  "src/transform.py"
  "src/load_bigquery.py"
  "src/config.py"
  "src/main.py"
  "tests/__init__.py"
  "tests/test_transform.py"
  "requirements.txt"
  "README.md"
  ".gitignore"
)

for directory in "${directories[@]}"; do
  mkdir -p "$directory"
  echo "Utworzono katalog: $directory"
done

for file in "${files[@]}"; do
  if [[ ! -e "$file" ]]; then
    touch "$file"
    echo "Utworzono plik: $file"
  else
    echo "Pominięto istniejący plik: $file"
  fi
done

cat > src/main.py <<'PYTHON'
def main() -> None:
    print("Steam BI Pipeline")


if __name__ == "__main__":
    main()
PYTHON

cat > README.md <<'MARKDOWN'
# Steam BI Pipeline

End-to-end data pipeline and Business Intelligence project using Steam data.

## Tech stack

- Python
- Pandas
- Steam API
- Google BigQuery
- Power BI

## Pipeline

```text
Steam API → Python → BigQuery → Power BI