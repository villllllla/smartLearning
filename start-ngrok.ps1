# 启动 ngrok 固定域名隧道 -> 本地后端 127.0.0.1:8000
# 固定域名（永久，不随重启变化）：glowworm-reactor-celestial.ngrok-free.dev
# 飞书「事件订阅 + 回调」请求地址：
#   https://glowworm-reactor-celestial.ngrok-free.dev/api/integrations/feishu/events

$ngrok = "C:\Users\zz34z\AppData\Local\Microsoft\WinGet\Packages\Ngrok.Ngrok_Microsoft.Winget.Source_8wekyb3d8bbwe\ngrok.exe"
if (-not (Test-Path $ngrok)) {
    $cmd = Get-Command ngrok -ErrorAction SilentlyContinue
    if ($cmd) { $ngrok = $cmd.Source } else { Write-Error "找不到 ngrok"; exit 1 }
}

& $ngrok http --url=https://glowworm-reactor-celestial.ngrok-free.dev 8000
