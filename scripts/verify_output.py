# -*- coding: utf-8 -*-
"""出包自检闸门：验证 flutter build 产出的 APK 可安装到 Android 5.1。

检查三项硬指标，任何一项不达标即 exit 1 让 CI 置红：
  1. AndroidManifest 的 minSdkVersion == 21（高于 21 则 Android 5.1 拒装）
  2. dex 版本为 035（037/038 是 Android 7.0/8.0 格式，5.1 的 ART 不识别）
  3. 存在 v1 签名 META-INF/MANIFEST.MF（Android 7.0 以下不识别 v2 签名）

失败时把 manifest 合并报告全文打进构建日志，便于定位是哪个依赖抬高了 minSdk。
"""
import glob
import struct
import sys
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
TARGET_MIN_SDK = 21
EXPECTED_DEX = b"035"


def axml_minsdk(data):
    strcount, stylecount, flags, strstart, stylestart = struct.unpack_from("<IIIII", data, 16)
    utf8 = (flags & (1 << 8)) != 0
    offs = struct.unpack_from("<%dI" % strcount, data, 36)
    base = 8 + strstart
    strings = []
    for o in offs:
        p = base + o
        if utf8:
            n = data[p]; p += 1
            if n & 0x80:
                n2 = data[p]; p += 1
                n = ((n & 0x7F) << 8) | n2
            m = data[p]; p += 1
            if m & 0x80:
                m = ((m & 0x7F) << 8) | data[p]; p += 1
            strings.append(data[p:p + m].decode("utf-8", "replace"))
        else:
            n = struct.unpack_from("<H", data, p)[0]; p += 2
            if n & 0x8000:
                n2 = struct.unpack_from("<H", data, p)[0]; p += 2
                n = ((n & 0x7FFF) << 16) | n2
            strings.append(data[p:p + n * 2].decode("utf-16-le", "replace"))
    _, _, sz = struct.unpack_from("<HHI", data, 8)
    o = 8 + sz
    t, hs, rsz = struct.unpack_from("<HHI", data, o)
    if t == 0x0180:
        o += rsz
    while o < len(data):
        t, hs, sz2 = struct.unpack_from("<HHI", data, o)
        if sz2 == 0:
            break
        if t == 0x0102:
            ns_, nm = struct.unpack_from("<iI", data, o + 16)
            a_start, a_size, a_count = struct.unpack_from("<HHH", data, o + 24)
            for i in range(a_count):
                ap = o + 16 + a_start + i * 20
                a_ns, a_name, a_raw, t_size, t_res0, t_type, t_data = struct.unpack_from("<IIIHBBI", data, ap)
                if strings[a_name] == "minSdkVersion":
                    return t_data
        o += sz2
    return None


def check_apk(path):
    problems = []
    z = zipfile.ZipFile(path)
    minsdk = axml_minsdk(z.read("AndroidManifest.xml"))
    if minsdk != TARGET_MIN_SDK:
        problems.append("minSdk=%s（应为 %d，Android 5.1 会拒装）" % (minsdk, TARGET_MIN_SDK))
    for name in z.namelist():
        if name.endswith(".dex"):
            magic = z.read(name)[:8]
            ver = magic[4:7]
            if ver != EXPECTED_DEX:
                problems.append("%s: dex 版本 %s（应为 %s，Android 5.1 的 ART 不识别）"
                                % (name, ver.decode("latin1"), EXPECTED_DEX.decode("latin1")))
    if "META-INF/MANIFEST.MF" not in z.namelist():
        problems.append("缺少 v1 签名 META-INF/MANIFEST.MF（Android 7.0 以下不识别 v2 签名）")
    return problems


def main():
    patterns = [
        "build/app/outputs/flutter-apk/*-release.apk",
        "android/app/build/outputs/flutter-apk/*-release.apk",
    ]
    apks = []
    for pat in patterns:
        apks += glob.glob(str(root / pat))
    apks = sorted(set(apks))
    if not apks:
        print("[verify] 未找到输出 APK！搜索过：")
        for pat in patterns:
            print("   -", root / pat)
        return 1

    failed = False
    for apk in apks:
        name = Path(apk).name
        try:
            problems = check_apk(apk)
        except Exception as e:  # noqa: BLE001
            print("[verify] FAIL %s：解析异常 %s" % (name, e))
            failed = True
            continue
        if problems:
            failed = True
            print("[verify] FAIL %s：" % name)
            for p in problems:
                print("       - %s" % p)
        else:
            print("[verify] PASS %s：minSdk=21 / dex=035 / v1 签名齐全" % name)

    if failed:
        print()
        print("======== 出包自检未通过：以下为 manifest 合并报告（定位 minSdk 抬升源） ========")
        report_pats = [
            "build/app/outputs/logs/manifest-merger-*-report.txt",
            "android/app/build/outputs/logs/manifest-merger-*-report.txt",
        ]
        found = False
        for pat in report_pats:
            for rep in glob.glob(str(root / pat)):
                found = True
                print("---- %s ----" % rep)
                try:
                    print(Path(rep).read_text(encoding="utf-8", errors="replace"))
                except Exception as e:  # noqa: BLE001
                    print("（读取失败：%s）" % e)
        if not found:
            print("（未找到 manifest 合并报告，搜索过：%s）" % "; ".join(report_pats))
        print("======== 报告结束 ========")
        return 1

    print("[verify] 全部通过：产物满足 Android 5.1 安装要求。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
