import subprocess
import sys
from pathlib import Path

MYPY_SUCCESS_EXIT_CODE = 0
MYPY_ERROR_EXIT_CODE = 1

FIXTURES_DIR = Path(__file__).parent / "root_cause_type_fixtures"


def _run_mypy(fixture_name: str) -> subprocess.CompletedProcess[str]:
    mypy_path = Path(sys.executable).with_name("mypy")
    return subprocess.run(
        [str(mypy_path), str(FIXTURES_DIR / fixture_name)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_root_cause_analysis_input_call_passes_type_check() -> None:
    result = _run_mypy("valid_call.py")

    assert result.returncode == MYPY_SUCCESS_EXIT_CODE, result.stdout


def test_raw_data_record_call_is_rejected_by_type_check() -> None:
    # 型分離(customer_idを含むRawDataRecordを外部LLM APIに渡せない)が
    # 崩れていないこと自体を検証するテスト。mypyのエラーメッセージ文言は
    # バージョンによって変わりうるため、exit codeを主基準にし、メッセージは
    # 対象クラス名を含むかという緩い部分一致に留める(完全一致にしない)。
    result = _run_mypy("invalid_call.py")

    assert result.returncode == MYPY_ERROR_EXIT_CODE, result.stdout
    assert "RawDataRecord" in result.stdout
