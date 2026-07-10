import argparse
from app.cli_functions import handle_health, detect_csv, detect_json, train_csv


def main():
    parser = argparse.ArgumentParser(
        description="Biodiv Outlier and Data-Quality Detection CLI Toolkit"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. Health Command
    subparsers.add_parser("status", help="Check local environment & Ollama status")

    # 2. Detect JSON Command
    json_parser = subparsers.add_parser(
        "detect-json", help="Run detection on a JSON file"
    )
    json_parser.add_argument(
        "--file", required=True, help="Path to the input JSON file"
    )
    json_parser.add_argument("--output", help="Custom path for output JSON file")
    json_parser.add_argument(
        "--enable-llm", action="store_true", help="Enable LLM reasoning"
    )
    json_parser.add_argument(
        "--use_ollama", action="store_true", help="Choice Ollama or OpenAI-o4"
    )
    json_parser.add_argument(
        "--semantic",
        dest="enable_semantic",
        action="store_true",
        help="Semantic checks",
    )
    json_parser.add_argument(
        "--rule-based",
        dest="enable_quality",
        action="store_true",
        help="Quality rule-based engine",
    )
    json_parser.set_defaults(handle_func=detect_json)

    # 3. Detect CSV Command
    csv_parser = subparsers.add_parser("detect-csv", help="Run detection on a CSV file")
    csv_parser.add_argument("--file", required=True, help="Path to input CSV file")
    csv_parser.add_argument("--output", help="Custom path for output CSV file")
    csv_parser.add_argument(
        "--enable-llm", action="store_true", help="Enable LLM reasoning"
    )
    csv_parser.add_argument(
        "--use_ollama", action="store_true", help="Choice Ollama or OpenAI-o4"
    )
    csv_parser.add_argument(
        "--chunksize", type=int, default=1000, help="Chunk tracking window size"
    )
    csv_parser.add_argument(
        "--max-records", type=int, help="Limit total rows to process"
    )
    csv_parser.add_argument(
        "--max-llm-records",
        type=int,
        default=25,
        help="Max items context limit for LLM checks",
    )
    csv_parser.add_argument(
        "--disable-llm-only-flagged",
        dest="llm_only_flagged",
        action="store_false",
        help="Evaluate all rows instead of only flagged items via LLM",
    )
    csv_parser.add_argument(
        "--semantic",
        dest="enable_semantic",
        action="store_true",
        help="Disable semantic checks",
    )
    csv_parser.add_argument(
        "--rule-based",
        dest="enable_quality",
        action="store_true",
        default=False,
        help="Enable quality checks",
    )
    csv_parser.set_defaults(handle_func=detect_csv)

    # 4. Train CSV Command
    train_parser = subparsers.add_parser(
        "train", help="Train models locally with a CSV file"
    )
    train_parser.add_argument(
        "--file", required=True, help="Path to training dataset CSV"
    )
    train_parser.add_argument(
        "--training-subset-size", type=int, default=500, help="Subset constraints size"
    )
    train_parser.add_argument(
        "--training-seed", type=int, default=42, help="Random engine seed value"
    )
    train_parser.set_defaults(handle_func=train_csv)

    args = parser.parse_args()

    if args.command == "status":
        handle_health()
    else:
        args.handle_func(args)


if __name__ == "__main__":
    main()
