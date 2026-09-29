from src.config import Settings
from src.infrastructure.sqlite_repository import SQLiteEquipmentRepository


def main() -> None:
    repository = SQLiteEquipmentRepository(Settings.from_environment().database_path)
    repository.initialize()
    repository.seed_if_empty()
    print(f"Seed data is ready: {repository.database_path}")


if __name__ == "__main__":
    main()
