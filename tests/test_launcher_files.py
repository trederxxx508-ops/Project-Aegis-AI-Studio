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

    # Baris komentar tidak diurai cmd.exe, jadi tidak ikut dihitung
    kode = [
        ln for ln in lines
        if not (ln.strip().upper().startswith("REM") or ln.strip().startswith("::"))
    ]
    teks_kode = "\n".join(kode)
    assert teks_kode.count("(") == teks_kode.count(")"), (
        f"{path.name}: kurung tidak seimbang pada baris kode"
    )


@pytest.mark.parametrize("path", BAT_FILES, ids=lambda p: p.name)
def test_no_unquoted_variable_expansion_inside_blocks(path):
    """``%VAR%`` tanpa kutip di dalam blok kurung adalah bom waktu.

    cmd.exe mengurai isi blok ``if ( ... )`` SEBELUM menjalankannya, dan
    ``%VAR%`` sudah disubstitusi saat itu. Bila nilainya mengandung tanda
    kurung — misalnya folder "Aegis (1)" hasil unduhan kedua — tanda ``)``
    menutup blok lebih awal dan skrip mati dengan "was unexpected at this
    time", bahkan ketika kondisi blok itu tidak terpenuhi.

    Ini benar-benar terjadi pada pengguna, dan tidak terlihat sama sekali
    saat diuji dengan path biasa.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    depth = 0
    offenders = []
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.upper().startswith("REM") or stripped.startswith("::"):
            continue
        if depth > 0:
            for m in re.finditer(r'(?<!")%([A-Za-z_][\w]*)%(?!")', line):
                offenders.append(f"baris {i}: %{m.group(1)}%")
        depth += line.count("(") - line.count(")")

    assert not offenders, (
        f"{path.name} memakai ekspansi variabel tanpa kutip di dalam blok "
        f"kurung: {'; '.join(offenders)}. Pindahkan ke label lewat goto, "
        "atau bungkus dengan tanda kutip."
    )


def test_error_paths_use_goto_not_blocks():
    """Percabangan galat harus lewat label, bukan blok kurung."""
    text = (ROOT / "JALANKAN-WINDOWS.bat").read_text(encoding="utf-8", errors="replace")
    assert "goto :galat_berkas" in text
    assert ":galat_berkas" in text
    assert "goto :galat_python_hilang" in text
    assert "goto :galat_pip" in text


def test_launcher_checks_the_files_it_needs():
    """Pemeriksaan awal harus menyebut berkas yang memang wajib ada."""
    text = (ROOT / "JALANKAN-WINDOWS.bat").read_text(encoding="utf-8", errors="replace")
    for wajib in ("requirements.txt", "rag_financial_api.py",
                  "streamlit_app.py", "market_data.py"):
        assert wajib in text, f"peluncur tidak memeriksa {wajib}"
        assert (ROOT / wajib).exists() or list(ROOT.rglob(wajib)), (
            f"{wajib} diperiksa peluncur tetapi tidak ada di repo"
        )
