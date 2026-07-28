"""Uji hubungan makro-emas terhadap data sungguhan — silakan jalankan sendiri.

    python scripts/validate_macro_relationship.py

Skrip ini menguji asumsi yang mendasari Macro Engine, dan sengaja disertakan
agar klaim apa pun tentang model ini bisa **Anda buktikan sendiri**, bukan
sekadar dipercaya.

Tiga pengujian, dan alasan mengapa urutannya penting:

1. Korelasi LEVEL suku bunga riil vs LEVEL harga emas.
   Uji ini **menyesatkan** dan sengaja ditampilkan sebagai peringatan: dua
   deret yang sama-sama menaik akan menghasilkan korelasi positif tinggi
   tanpa ada hubungan sebab-akibat apa pun (korelasi semu).

2. Korelasi PERUBAHAN suku bunga riil vs IMBAL HASIL emas — uji yang benar
   untuk hubungan sewaktu (contemporaneous).

3. Apakah kondisi hari ini MERAMALKAN imbal hasil emas ke depan. Ini yang
   paling menentukan: hubungan sewaktu tidak bisa dijadikan dasar keputusan
   kalau tidak punya daya ramal.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import macro_engine, market_data  # noqa: E402

FORWARD_DAYS = 63  # sekitar 3 bulan perdagangan


def _aligned_series():
    real_yield = dict(macro_engine.fetch_fred_series("DFII10", use_cache=False))
    gold_df = market_data.fetch_chart_api("GC=F", range_="10y")
    gold = {d.date(): float(v) for d, v in gold_df["Close"].dropna().items()}
    days = sorted(set(real_yield) & set(gold))
    return (
        days,
        np.array([real_yield[d] for d in days]),
        np.array([gold[d] for d in days]),
    )


def main() -> None:
    days, ry, gold = _aligned_series()
    print(f"Data: {len(days)} hari beririsan, {days[0]} s/d {days[-1]}\n")

    print("=" * 72)
    print("1. LEVEL vs LEVEL — uji yang MENYESATKAN (ditampilkan sebagai peringatan)")
    print("=" * 72)
    print(f"   korelasi level: {np.corrcoef(ry, gold)[0, 1]:+.3f}")
    print("   Dua deret yang sama-sama menaik selalu berkorelasi tinggi.")
    print("   Angka ini TIDAK boleh dipakai menyimpulkan apa pun.\n")

    print("=" * 72)
    print("2. PERUBAHAN vs IMBAL HASIL — uji hubungan sewaktu yang benar")
    print("=" * 72)
    print("   Teori: suku bunga riil naik -> emas turun (korelasi negatif)")
    for label, n in [("harian", 1), ("mingguan", 5), ("bulanan", 21), ("kuartalan", 63)]:
        d_ry = ry[n:] - ry[:-n]
        ret = (gold[n:] - gold[:-n]) / gold[:-n] * 100
        corr = np.corrcoef(d_ry, ret)[0, 1]
        verdict = "sesuai teori" if corr < -0.1 else "berlawanan" if corr > 0.1 else "tak ada hubungan"
        print(f"   {label:10}: {corr:+.3f}  ({verdict})")
    print()

    print("=" * 72)
    print("3. DAYA RAMAL — apakah kondisi hari ini meramalkan emas 3 bulan ke depan?")
    print("=" * 72)
    forward = (gold[FORWARD_DAYS:] - gold[:-FORWARD_DAYS]) / gold[:-FORWARD_DAYS] * 100
    level = ry[:-FORWARD_DAYS]
    change = ry[FORWARD_DAYS:-FORWARD_DAYS] - ry[: -2 * FORWARD_DAYS]

    print(f"   korelasi LEVEL     vs imbal hasil ke depan: {np.corrcoef(level, forward)[0, 1]:+.3f}")
    print(f"   korelasi PERUBAHAN vs imbal hasil ke depan: "
          f"{np.corrcoef(change, forward[FORWARD_DAYS:])[0, 1]:+.3f}")
    print()
    print("   Rata-rata imbal hasil emas 3 bulan berikutnya, per level suku bunga riil:")
    print("   (model menilai level RENDAH sebagai baik untuk emas — periksa apakah benar)")
    for lo, hi in [(-2, 0), (0, 1), (1, 2), (2, 3), (3, 5)]:
        mask = (level >= lo) & (level < hi)
        if mask.sum() > 30:
            print(f"     riil {lo:+.0f}%..{hi:+.0f}% : {forward[mask].mean():+6.2f}%  ({mask.sum():4} hari)")
    print()
    print("   Rata-rata imbal hasil emas 3 bulan berikutnya, per ARAH perubahan:")
    fwd_c = forward[FORWARD_DAYS:]
    for label, mask in [
        ("sedang turun", change < -0.15),
        ("datar", np.abs(change) <= 0.15),
        ("sedang naik", change > 0.15),
    ]:
        if mask.sum() > 30:
            print(f"     {label:13}: {fwd_c[mask].mean():+6.2f}%  ({mask.sum():4} hari)")

    print()
    print("=" * 72)
    print("CATATAN KETERBATASAN — wajib dibaca sebelum menyimpulkan")
    print("=" * 72)
    print("""   - Sepuluh tahun terakhir hanyalah SATU rezim pasar, dan emas naik
     hampir sepanjang periode itu. Semua kelompok akan tampak positif.
   - Jendela 3 bulan saling tumpang tindih, sehingga jumlah pengamatan yang
     benar-benar independen jauh lebih sedikit daripada jumlah barisnya.
   - Sejak 2022 pembelian besar-besaran oleh bank sentral mendorong emas naik
     bersamaan dengan naiknya suku bunga riil — faktor perancu yang tidak
     tertangkap oleh model ini.
   Kesimpulan yang bisa dipertanggungjawabkan: hubungan SEWAKTU nyata,
   tetapi DAYA RAMAL-nya tidak terbukti. Skor makro menggambarkan kondisi
   saat ini, bukan ramalan harga.""")


if __name__ == "__main__":
    main()
