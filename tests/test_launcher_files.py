"""Test berkas peluncur — mencegah kelas galat yang tidak terlihat di Linux.

Berkas batch Windows **wajib** memakai akhir baris CRLF. Dengan LF saja,
cmd.exe salah membaca blok ``if (...)`` dan label ``goto``: sebagian baris
tidak tercetak dan pemeriksaan gagal walau berkasnya ada — tanpa pesan galat
yang menunjukkan penyebabnya.

Kegagalan ini tidak pernah muncul saat pengembangan di Linux, sehingga hanya
terungkap setelah dijalankan di Windows sungguhan. Test ini membuatnya
tertangkap otomatis sejak awal.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BAT_FILES = sorted(ROOT.glob("*.bat"))
SH_FILES = sorted(ROOT.glob("*.sh"))


def test_batch_files_exist():
    names = {p.name for p in BAT_FILES}
    assert "JALANKAN-WINDOWS.bat" in names
    assert "PASANG-AEGIS.bat" in names


@pytest.mark.parametrize("path", BAT_FILES, ids=lambda p: p.name)
def test_batch_files_use_crlf(path):
    """Setiap baris berkas .bat harus diakhiri CRLF."""
    data = path.read_bytes()
    total = data.count(b"\n")
    crlf = data.count(b"\r\n")
    assert total > 0, f"{path.name} kosong"
    assert crlf == total, (
        f"{path.name}: hanya {crlf} dari {total} baris memakai CRLF. "
        "cmd.exe akan salah membaca blok if/goto dan gagal secara diam-diam."
    )


@pytest.mark.parametrize("path", SH_FILES, ids=lambda p: p.name)
def test_shell_scripts_use_lf(path):
    """Sebaliknya, skrip shell rusak bila memakai CRLF."""
    data = path.read_bytes()
    assert b"\r\n" not in data, (
        f"{path.name} memakai CRLF; bash akan gagal dengan galat seperti "
        "'$'\\r': command not found'."
    )


def test_gitattributes_locks_line_endings():
    """Tanpa .gitattributes, git bisa mengembalikan akhir baris ke LF."""
    ga = ROOT / ".gitattributes"
    assert ga.exists(), ".gitattributes wajib ada agar CRLF tidak hilang"
    isi = ga.read_text()
    assert "*.bat text eol=crlf" in isi
    assert "*.sh text eol=lf" in isi


@pytest.mark.parametrize("path", BAT_FILES, ids=lambda p: p.name)
def test_batch_structure_is_sound(path):
    """Kurung seimbang, label tidak di dalam blok, goto menunjuk label yang ada."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    labels = {
        s.strip().lstrip(":").lower()
        for s in lines if re.match(r"^\s*:[a-zA-Z]", s)
    }

    depth = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.upper().startswith("REM") or stripped.startswith("::"):
            continue
        if re.match(r"^:[a-zA-Z]", stripped):
            assert depth == 0, (
                f"{path.name} baris {i}: label '{stripped}' berada di dalam blok "
                "kurung — melompat ke sana merusak konteks blok."
            )
        for m in re.finditer(r"\bgoto\s+:?([a-zA-Z_]\w*)", line, re.I):
            assert m.group(1).lower() in labels, (
                f"{path.name} baris {i}: goto ke label tak dikenal '{m.group(1)}'"
            )
        depth += line.count("(") - line.count(")")

    assert text.count("(") == text.count(")"), (
        f"{path.name}: kurung tidak seimbang"
    )


def test_launcher_checks_the_files_it_needs():
    """Pemeriksaan awal harus menyebut berkas yang memang wajib ada."""
    text = (ROOT / "JALANKAN-WINDOWS.bat").read_text(encoding="utf-8", errors="replace")
    for wajib in ("requirements.txt", "rag_financial_api.py",
                  "streamlit_app.py", "market_data.py"):
        assert wajib in text, f"peluncur tidak memeriksa {wajib}"
        assert (ROOT / wajib).exists() or list(ROOT.rglob(wajib)), (
            f"{wajib} diperiksa peluncur tetapi tidak ada di repo"
        )
