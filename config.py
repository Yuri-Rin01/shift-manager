import os

# care | hospital | all（両方のマスタを統合）
FACILITY_TYPE = os.getenv("FACILITY_TYPE", "care").lower()

# サイドバー等に表示する施設名
FACILITY_NAME = os.getenv("FACILITY_NAME", "○○施設")
