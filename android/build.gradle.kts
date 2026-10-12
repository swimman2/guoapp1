allprojects {
    repositories {
        // 本地补丁仓库置于最前：prepare_local_maven.py 会把去掉了
        // uses-sdk(minSdk=24) 声明的 ffmpeg-kit AAR 放到这里，
        // 使 Gradle 优先解析该副本，从源头阻止依赖抬高最终 minSdk。
        maven { url = uri(rootProject.projectDir.resolve("local-maven")) }
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}

// 把所有 Android 库子模块声明的高于 21 的 minSdk 统一压回 21，
// 防止插件模块（如 ffmpeg_kit、video_player_android 声明的 minSdk=24）
// 在 manifest 合并时抬高最终 APK 的 minSdk。
// 注意：此块必须放在 evaluationDependsOn(":app") 之前——后者会立即触发
// :app 求值，之后再对已求值工程注册 afterEvaluate 会直接构建失败；
// app 模块自身已显式 minSdk=21，一并跳过。
// 全程反射 + runCatching，兼容新旧 DSL，任何失败只打日志、不中断构建。
subprojects {
    if (project.name != "app") {
        afterEvaluate {
            val androidExt = extensions.findByName("android") ?: return@afterEvaluate
            runCatching {
                val dc = androidExt.javaClass.getMethod("getDefaultConfig").invoke(androidExt)
                val cur = (runCatching { dc.javaClass.getMethod("getMinSdk").invoke(dc) as? Int }.getOrNull()
                    ?: runCatching {
                        dc.javaClass.getMethod("getMinSdkVersion").invoke(dc)?.toString()?.toIntOrNull()
                    }.getOrNull()
                    ?: 0)
                if (cur > 21) {
                    val lowered = dc.javaClass.methods.any { m ->
                        m.name == "setMinSdk" && m.parameterCount == 1 &&
                            runCatching { m.invoke(dc, 21); true }.getOrDefault(false)
                    } || dc.javaClass.methods.any { m ->
                        m.name == "setMinSdkVersion" && m.parameterCount == 1 &&
                            runCatching { m.invoke(dc, 21); true }.getOrDefault(false)
                    }
                    println(
                        if (lowered) "[minSdk-force] ${project.name}: minSdk $cur -> 21"
                        else "[minSdk-force] ${project.name}: minSdk=$cur，未能自动降级"
                    )
                }
            }
        }
    }
}

subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
