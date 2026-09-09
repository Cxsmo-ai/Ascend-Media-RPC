param (
    [string]$ApiKey,
    [string]$Action,
    [string]$Magnet
)

$BaseUrl = "https://www.deepbrid.com/api/v1"
$Headers = @{
    "Authorization" = "Bearer $ApiKey"
}

function List-Downloads {
    try {
        $url = "$BaseUrl/downloads"
        $resp = Invoke-RestMethod -Uri $url -Headers $Headers
        
        if ($resp.success -eq $true) {
            $items = $resp.data
            if (!$items -or $items.Count -eq 0) {
                Write-Host "No unlocked downloads found. Check 'Active Torrents' if you just added something."
                return
            }
            Write-Host "Finished / Unlocked Downloads:"
            for ($i=0; $i -lt $items.Count; $i++) {
                Write-Host "[$i] $($items[$i].name)"
            }
            $choice = Read-Host "`nSelect item number to get link (or 'b' for back)"
            if ($choice -ne 'b' -and $choice -match '^\d+$' -and $choice -lt $items.Count) {
                $selected = $items[$choice]
                Write-Host "`nTitle: $($selected.name)"
                Write-Host "Link: $($selected.download_url)"
                try {
                    $selected.download_url | Set-Clipboard
                    Write-Host "(Link copied to clipboard!)"
                } catch {
                    Write-Host "(Note: Could not copy to clipboard automatically)"
                }
            }
        } else {
            Write-Host "API Error: $($resp.message)"
        }
    } catch {
        Write-Host "Request failed: $($_.Exception.Message)"
    }
}

function List-Torrents {
    try {
        $url = "$BaseUrl/torrents/list"
        $resp = Invoke-RestMethod -Uri $url -Headers $Headers
        
        # DEBUG: Write-Host "Raw Response: $($resp | ConvertTo-Json -Depth 2)"

        if ($resp.success -eq $true) {
            $items = $resp.data
            if (!$items -or $items.Count -eq 0) {
                Write-Host "No torrents found in your cloud."
                return
            }
            Write-Host "Torrents in Cloud:"
            for ($i=0; $i -lt $items.Count; $i++) {
                $item = $items[$i]
                Write-Host "[$i] [$($item.status)] $($item.name) ($($item.progress)%)"
            }
            
            $choice = Read-Host "`nSelect item number to view details/files (or 'b' for back)"
            if ($choice -ne 'b' -and $choice -match '^\d+$' -and $choice -lt $items.Count) {
                $selected = $items[$choice]
                Get-Torrent-Info -TorrentId $selected.id
            }
        } else {
            Write-Host "API Error: $($resp.message)"
        }
    } catch {
        Write-Host "Request failed: $($_.Exception.Message)"
    }
}

function Get-Torrent-Info {
    param([string]$TorrentId)
    try {
        $url = "$BaseUrl/torrents/info?id=$TorrentId"
        $resp = Invoke-RestMethod -Uri $url -Headers $Headers
        if ($resp.success -eq $true) {
            $data = $resp.data
            Write-Host "`nTorrent: $($data.name)"
            Write-Host "Status: $($data.status)"
            Write-Host "Files:"
            $files = $data.files
            for ($i=0; $i -lt $files.Count; $i++) {
                Write-Host "  [$i] $($files[$i].name) ($([math]::Round($files[$i].size / 1MB, 2)) MB)"
            }
            
            if ($data.status -eq 'downloaded') {
                $fChoice = Read-Host "`nSelect file number to generate playable link (or 'b' for back)"
                if ($fChoice -ne 'b' -and $fChoice -match '^\d+$' -and $fChoice -lt $files.Count) {
                    $selectedFile = $files[$fChoice]
                    # Generate link for this file
                    Generate-Link -Link $selectedFile.link
                }
            } else {
                Write-Host "`nTorrent is still downloading ($($data.progress)%). Wait until it's 'downloaded' to generate links."
            }
        } else {
            Write-Host "API Error: $($resp.message)"
        }
    } catch {
        Write-Host "Request failed: $($_.Exception.Message)"
    }
}

function Generate-Link {
    param([string]$Link)
    try {
        Write-Host "Generating playable link..."
        $params = @{
            link = $Link
        }
        $url = "$BaseUrl/download"
        $resp = Invoke-WebRequest -Method Post -Uri $url -Headers $Headers -Body $params
        $json = $resp.Content | ConvertFrom-Json
        if ($json.success -eq $true) {
            Write-Host "`nPlayable Link Generated!"
            Write-Host "Link: $($json.data.download_url)"
            $json.data.download_url | Set-Clipboard
            Write-Host "(Link copied to clipboard!)"
        } else {
            Write-Host "Error generating link: $($json.message)"
        }
    } catch {
        Write-Host "Request failed: $($_.Exception.Message)"
    }
}

function Add-Magnet {
    try {
        $params = @{
            magnet = $Magnet
        }
        $url = "$BaseUrl/torrents/add"
        $resp = Invoke-WebRequest -Method Post -Uri $url -Headers $Headers -Body $params
        $json = $resp.Content | ConvertFrom-Json
        if ($json.success -eq $true) {
            Write-Host "Successfully added torrent: $($json.data.name)"
        } else {
            Write-Host "Error adding magnet: $($json.message)"
        }
    } catch {
        Write-Host "Request failed: $($_.Exception.Message)"
    }
}

switch ($Action) {
    "list_downloads" { List-Downloads }
    "list_torrents" { List-Torrents }
    "add_magnet" { Add-Magnet }
}
