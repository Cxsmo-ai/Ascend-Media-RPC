$key = "86a9618a6d0ce3610df6ccb7b4c77fb927eb1d98f81e5de0704c4afdb7ee75dc"
$endpoints = @(
    "torrents",
    "torrents/list",
    "torrents/status",
    "torrents/all",
    "downloads",
    "downloads/list",
    "history",
    "user/torrents",
    "user/downloads",
    "account",
    "user/account",
    "generate/link",
    "torrents/add"
)

foreach ($e in $endpoints) {
    $url = "https://www.deepbrid.com/api/v1/" + $e + "?apikey=" + $key
    Write-Host "Testing GET: $url"
    try {
        $resp = Invoke-WebRequest -Uri $url -Method Get -ErrorAction Stop -TimeoutSec 5
        Write-Host "SUCCESS: $url"
        Write-Host "Content: $($resp.Content.Substring(0, [math]::Min(200, $resp.Content.Length)))"
    } catch {
        $status = if ($_.Exception.Response) { $_.Exception.Response.StatusCode } else { "Unknown" }
        Write-Host "FAIL ($status): $url"
    }
}
