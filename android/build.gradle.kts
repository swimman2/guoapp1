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

// 把所有 Android 模块（含 app 自身）声明的高于 21 的 minSdk 统一压回 21。
// app 模块也纳入：即使 minSdk 被某种构建期改写抬高（如 flutter 工具迁移），
// 此处在 AGP 完成变体定稿前强制改回。注意：此块必须放在
// evaluationDependsOn(":app") 之前——后者会立即触发 :app 求值，
// 之后再对已求值工程注册 afterEvaluate 会直接构建失败。
// 全程反射 + runCatching，兼容新旧 DSL，任何失败只打日志、不中断构建。
subprojects {
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

subprojects {
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
