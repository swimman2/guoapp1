"""把 pub 缓存中各 Flutter 插件声明的高 minSdk 统一降到 21。

背景：AGP 9 的 manifest 合并会把依赖库声明的 minSdk 上限合并进最终 APK。
应用层 minSdk = 21 时，若依赖（如 ffmpeg_kit_flutter_new_min_gpl 声明 24）
保持高值，最终 APK 的 minSdk 会被抬回 24，导致 dex 版本、签名方案跟着
回到 Android 7+ 体系。在 flutter pub get 之后、flutter build 之前运行
本脚本，从 pub 缓存源头消除抬升。

说明：仅改插件的 Gradle 声明，不触碰其预编译 .so（如 ffmpeg_kit 的
.so 按 API 24 编译，但只在调用 FFmpeg 功能时才惰性加载，不影响常规
播放，装到低版本设备亦不崩溃）。
"""

import os
import re
import sys
from pathlib import Path

TARGET = 21

# 兼容 Groovy（minSdkVersion 24 / minSdk 24）与 KTS（minSdk = 24）写法，
# 以及跟随 Flutter 默认值的 flutter.minSdkVersion 引用。
MINSDK_RE = re.compile(
    r'(minSdk(?:Version)?)(\s*=\s*|\s+)(\d+|flutter\.minSdkVersion)')


def pub_cache_roots():
    roots = []
    env_cache = os.environ.get('PUB_CACHE')
    if env_cache:
        roots.append(Path(env_cache))
    roots.append(Path.home() / '.pub-cache')
    return roots


def patch_gradle_file(path):
    """返回该文件中被改动的 minSdk 声明列表。"""
    try:
        text = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return []

    changes = []

    def repl(match):
        name, sep, value = match.group(1), match.group(2), match.group(3)
        if value == 'flutter.minSdkVersion':
            changes.append('%s %s -> %d' % (name, value, TARGET))
            return '%s%s%d' % (name, sep, TARGET)
        number = int(value)
        if number <= TARGET:
            return match.group(0)
        changes.append('%s %d -> %d' % (name, number, TARGET))
        return '%s%s%d' % (name, sep, TARGET)

    new_text = MINSDK_RE.sub(repl, text)
    if changes:
        path.write_text(new_text, encoding='utf-8')
    return changes


def main():
    total_packages = 0
    total_changes = 0
    for root in pub_cache_roots():
        if not root.is_dir():
            continue
        # 覆盖 pub 缓存的常见层级：hosted/<registry>/<package>/android/…、
        # git/<package>/android/…，以及极少数直接平铺的 <package>/android/…。
        patterns = (
            'hosted/*/*/android/build.gradle',
            'hosted/*/*/android/build.gradle.kts',
            'git/*/android/build.gradle',
            'git/*/android/build.gradle.kts',
            '*/android/build.gradle',
            '*/android/build.gradle.kts',
        )
        for pattern in patterns:
            for gradle in root.glob(pattern):
                changes = patch_gradle_file(gradle)
                if changes:
                    total_packages += 1
                    total_changes += len(changes)
                    package = gradle.parent.parent.name
                    print('[lower_dep_minsdk] %s: %s' % (package, ', '.join(changes)))
    print('[lower_dep_minsdk] 完成：改写 %d 个插件、%d 处 minSdk 声明（目标值 %d）。'
          % (total_packages, total_changes, TARGET))
    if total_changes == 0:
        print('[lower_dep_minsdk] 警告：未发现需要降级的插件，请确认 pub 缓存已就绪。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
