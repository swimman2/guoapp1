# -*- coding: utf-8 -*-
"""准备本地补丁 Maven 仓库。

com.antonkarpenko:ffmpeg-kit-min-gpl:2.2.2 的 AAR 内嵌 AndroidManifest.xml
声明 minSdkVersion=24（包名 com.antonkarpenko）。AGP 的 manifest 合并会把它
抬高到最终 APK，抵消应用层 minSdk=21。本脚本从 Maven Central 下载该 AAR，
去掉其中的 uses-sdk 声明后安装到 android/local-maven，配合根 build.gradle.kts
里置于最前的本地仓库声明，使 Gradle 优先解析这份干净的副本。

下载失败时仅告警并正常退出（exit 0）：此时退回依靠 manifest 的
overrideLibrary 覆盖，最终由 verify_output.py 出包自检兜底。
"""
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
GROUP_PATH = "com/antonkarpenko/ffmpeg-kit-min-gpl/2.2.2"
BASE = "https://repo1.maven.org/maven2/" + GROUP_PATH
AAR_NAME = "ffmpeg-kit-min-gpl-2.2.2.aar"
POM_NAME = "ffmpeg-kit-min-gpl-2.2.2.pom"
MODULE_NAME = "ffmpeg-kit-min-gpl-2.2.2.module"

target_dir = root / "android" / "local-maven" / GROUP_PATH


def fetch(url, timeout=600):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def main():
    if (target_dir / AAR_NAME).exists():
        print("[local-maven] 已存在，跳过:", target_dir / AAR_NAME)
        return 0

    try:
        print("[local-maven] 下载", BASE + "/" + AAR_NAME, flush=True)
        aar_bytes = fetch(BASE + "/" + AAR_NAME)
    except Exception as e:  # noqa: BLE001
        print("[local-maven] 警告：AAR 下载失败（%s）。" % e)
        print("[local-maven] 本次跳过本地替换，依靠 overrideLibrary + 出包自检兜底。")
        return 0

    src = zipfile.ZipFile(io.BytesIO(aar_bytes))
    manifest = src.read("AndroidManifest.xml").decode("utf-8", "replace")
    print("[local-maven] 原 manifest:")
    print(manifest)
    patched = "\n".join(ln for ln in manifest.splitlines() if "<uses-sdk" not in ln) + "\n"
    print("[local-maven] 补丁后 manifest:")
    print(patched)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            if info.filename == "AndroidManifest.xml":
                continue
            zi = zipfile.ZipInfo(info.filename, date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            dst.writestr(zi, src.read(info.filename))
        zi = zipfile.ZipInfo("AndroidManifest.xml", date_time=(2026, 1, 1, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_DEFLATED
        dst.writestr(zi, patched.encode("utf-8"))

    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / AAR_NAME).write_bytes(out.getvalue())
    print("[local-maven] 已写入", target_dir / AAR_NAME,
          "(%d 字节)" % (target_dir / AAR_NAME).stat().st_size)

    for name in (POM_NAME, MODULE_NAME):
        try:
            (target_dir / name).write_bytes(fetch(BASE + "/" + name))
            print("[local-maven] 已写入", target_dir / name)
        except Exception:  # noqa: BLE001 - module 元数据可能不存在，pom 失败也可回退
            print("[local-maven] %s 未获取（可忽略）" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
