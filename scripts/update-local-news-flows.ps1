param(
    [string]$ApiBase = "http://127.0.0.1:8090",
    [string]$ApiToken = $env:SIFTLANE_ENGINE_API_TOKEN
)

$ErrorActionPreference = "Stop"
function ConvertFrom-UnicodeLiteral {
    param([string]$Value)
    return [regex]::Unescape($Value)
}

function Invoke-SiftLaneJson {
    param(
        [string]$Method,
        [string]$Uri,
        [string]$Body = ""
    )

    $client = New-Object System.Net.WebClient
    $client.Encoding = [System.Text.Encoding]::UTF8
    if ($ApiToken) {
        $client.Headers["Authorization"] = "Bearer $ApiToken"
    }
    try {
        if ($Method -eq "GET") {
            $json = $client.DownloadString($Uri)
        }
        else {
            $client.Headers["Content-Type"] = "application/json; charset=utf-8"
            $json = $client.UploadString($Uri, $Method, $Body)
        }
        return $json | ConvertFrom-Json
    }
    catch [System.Net.WebException] {
        $response = $_.Exception.Response
        if ($null -ne $response) {
            $reader = New-Object System.IO.StreamReader($response.GetResponseStream(), [System.Text.Encoding]::UTF8)
            try {
                $detail = $reader.ReadToEnd()
            }
            finally {
                $reader.Dispose()
                $response.Dispose()
            }
            throw "$Method $Uri failed: $detail"
        }
        throw
    }
    finally {
        $client.Dispose()
    }
}

$hotspot = ConvertFrom-UnicodeLiteral "\u70ed\u70b9"
$bbcChinese = "BBC " + (ConvertFrom-UnicodeLiteral "\u4e2d\u6587")
$peopleOnline = ConvertFrom-UnicodeLiteral "\u4eba\u6c11\u7f51"
$chinaNews = ConvertFrom-UnicodeLiteral "\u4e2d\u56fd\u65b0\u95fb\u7f51"
$cctvNews = ConvertFrom-UnicodeLiteral "\u592e\u89c6\u65b0\u95fb"
$xinhuanet = ConvertFrom-UnicodeLiteral "\u65b0\u534e\u7f51"

function New-NewsFlowDefinition {
    param([hashtable]$Spec)

    return @{
        name = $Spec.Name
        description = "Collect hotspot listings, fetch every article detail page, and emit full content, author, and publication time."
        enabled = $true
        visibility = "team"
        max_items = $Spec.MaxItems
        timeout_seconds = 3600
        parameter_schema = @{ type = "object" }
        nodes = @(
            @{
                id = "start"
                type = "start"
                name = "Hotspot sources"
                x = 80
                y = 220
                config = @{ urls = $Spec.Urls }
            },
            @{
                id = "listing_request"
                type = "http_request"
                name = "Fetch listings"
                x = 330
                y = 220
                config = @{
                    url = "{{url}}"
                    respect_robots = $true
                    fallback_to_http = $true
                    force_http = [bool]$Spec.ForceHttp
                    continue_on_error = $true
                    timeout_seconds = 20
                }
                retry = @{
                    max_attempts = 3
                    backoff_seconds = 1
                    max_backoff_seconds = 4
                    retryable_statuses = @(408, 429, 500, 502, 503, 504)
                    retryable_errors = @("TimeoutError", "ReadTimeout", "ConnectError", "ConnectionError", "RemoteProtocolError", "HTTPStatusError")
                }
            },
            @{
                id = "listing_extract"
                type = $Spec.ListType
                name = "Extract article links"
                x = 580
                y = 220
                config = $Spec.ListConfig
            },
            @{
                id = "detail_request"
                type = "http_request"
                name = "Fetch article details"
                x = 830
                y = 220
                config = @{
                    url = "{{url}}"
                    respect_robots = $true
                    continue_on_error = $true
                    fallback_to_http = $true
                    force_http = [bool]$Spec.ForceHttp
                    timeout_seconds = 15
                }
                retry = @{
                    max_attempts = 2
                    backoff_seconds = 1
                    max_backoff_seconds = 4
                    retryable_statuses = @(408, 429, 500, 502, 503, 504)
                    retryable_errors = @("TimeoutError", "ReadTimeout", "ConnectError", "ConnectionError", "RemoteProtocolError", "HTTPStatusError")
                }
            },
            @{
                id = "detail_extract"
                type = "html_extract"
                name = "Extract full articles"
                x = 1080
                y = 220
                config = @{
                    item_selector = ""
                    fields = $Spec.DetailFields
                }
            },
            @{
                id = "emit"
                type = "emit"
                name = "Emit complete articles"
                x = 1330
                y = 220
                config = @{
                    skip_empty_content = $true
                    fields = @{
                        title = "{{detail_title}}"
                        url = "{{listing_url}}"
                        external_id = "{{listing_url}}"
                        content = "{{content}}"
                        media_type = "text/html"
                        metadata = @{
                            source = $Spec.Source
                            originSource = "{{origin_source}}"
                            author = "{{author}}"
                            sourceAuthorId = "{{source_author_id}}"
                            publishedAt = "{{published_at}}"
                            listingTitle = "{{title}}"
                            listingUrl = "{{listing_url}}"
                            detailUrl = "{{url}}"
                            captureMode = "listing-to-detail"
                        }
                    }
                }
            }
        )
        edges = @(
            @{ id = "e1"; source = "start"; target = "listing_request" },
            @{ id = "e2"; source = "listing_request"; target = "listing_extract" },
            @{ id = "e3"; source = "listing_extract"; target = "detail_request" },
            @{ id = "e4"; source = "detail_request"; target = "detail_extract" },
            @{ id = "e5"; source = "detail_extract"; target = "emit" }
        )
    }
}

$specs = @(
    @{
        Name = "$bbcChinese$hotspot"
        Source = $bbcChinese
        MaxItems = 300
        ForceHttp = $false
        Urls = @(
            "https://www.bbc.com/zhongwen/topics/c83plve5vmjt/simp",
            "https://www.bbc.com/zhongwen/topics/ckr7mn6r003t/simp",
            "https://www.bbc.com/zhongwen/topics/cezw73jk755t/simp",
            "https://www.bbc.com/zhongwen/topics/cd6qem06z92t/simp",
            "https://www.bbc.com/zhongwen/topics/c1ez1k4emn0t/simp",
            "https://www.bbc.com/zhongwen/topics/cq8nqywy37yt/simp",
            "https://www.bbc.com/zhongwen/topics/cgvl47l38e1t/simp"
        )
        ListType = "html_extract"
        ListConfig = @{
            item_selector = 'h2 a[href*="/zhongwen/articles/"], h3 a[href*="/zhongwen/articles/"]'
            deduplicate_by = "url"
            fields = @{
                title = @{ selector = ""; attribute = "text" }
                url = @{ selector = ""; attribute = "href" }
                listing_url = @{ selector = ""; attribute = "href" }
            }
        }
        DetailFields = @{
            detail_title = "main h1"
            content = @{
                selector = 'main div[dir="ltr"] > p'
                attribute = "text"
                all = $true
                separator = "`n`n"
            }
            author = @{
                selector = 'script[type="application/ld+json"]'
                attribute = "json"
                path = "@graph.0.author.name"
            }
            published_at = @{ selector = 'meta[name="article:published_time"]'; attribute = "content" }
            origin_source = @{ selector = 'meta[property="og:site_name"]'; attribute = "content"; default = $bbcChinese }
        }
    },
    @{
        Name = "$peopleOnline$hotspot"
        Source = $peopleOnline
        MaxItems = 300
        ForceHttp = $false
        Urls = @(
            "http://www.people.com.cn/",
            "http://politics.people.com.cn/",
            "http://world.people.com.cn/",
            "http://finance.people.com.cn/",
            "http://society.people.com.cn/",
            "http://opinion.people.com.cn/",
            "http://health.people.com.cn/",
            "http://military.people.com.cn/"
        )
        ListType = "html_extract"
        ListConfig = @{
            item_selector = 'a[href*="/n1/2026/"][href$=".html"]:not(:has(img)):not(:empty)'
            deduplicate_by = "url"
            fields = @{
                title = @{ selector = ""; attribute = "text" }
                url = @{ selector = ""; attribute = "href" }
                listing_url = @{ selector = ""; attribute = "href" }
            }
        }
        DetailFields = @{
            detail_title = "h1"
            content = @{ selector = "#rm_txt_zw p"; attribute = "text"; all = $true; separator = "`n`n" }
            author = @{ selector = '#rm_txt_zw [class*="author"]'; attribute = "text" }
            published_at = "#newstime"
            origin_source = @{ selector = 'meta[name="source"]'; attribute = "content"; default = $peopleOnline }
        }
    },
    @{
        Name = "$chinaNews$hotspot"
        Source = $chinaNews
        MaxItems = 300
        ForceHttp = $false
        Urls = @(
            "https://www.chinanews.com.cn/",
            "https://www.chinanews.com.cn/gn/",
            "https://www.chinanews.com.cn/gj/",
            "https://www.chinanews.com.cn/cj/",
            "https://www.chinanews.com.cn/sh/",
            "https://www.chinanews.com.cn/cul/"
        )
        ListType = "html_extract"
        ListConfig = @{
            item_selector = 'a[href*="/2026/"][href$=".shtml"]:not(:has(img)):not(:empty)'
            deduplicate_by = "url"
            fields = @{
                title = @{ selector = ""; attribute = "text" }
                url = @{ selector = ""; attribute = "href" }
                listing_url = @{ selector = ""; attribute = "href" }
            }
        }
        DetailFields = @{
            detail_title = "h1, .content_title .title"
            content = @{ selector = ".left_zw p, .content_desc p"; attribute = "text"; all = $true; separator = "`n`n" }
            author = "#author_baidu"
            published_at = "#pubtime_baidu, .content_title .left p"
            origin_source = "#source_baidu, .content_title .left p"
        }
    },
    @{
        Name = "$cctvNews$hotspot"
        Source = $cctvNews
        MaxItems = 300
        ForceHttp = $true
        Urls = @(
            "https://news.cctv.com/2019/07/gaiban/cmsdatainterface/page/china_1.jsonp",
            "https://news.cctv.com/2019/07/gaiban/cmsdatainterface/page/china_2.jsonp",
            "https://news.cctv.com/2019/07/gaiban/cmsdatainterface/page/china_3.jsonp",
            "https://news.cctv.com/2019/07/gaiban/cmsdatainterface/page/world_1.jsonp",
            "https://news.cctv.com/2019/07/gaiban/cmsdatainterface/page/world_2.jsonp",
            "https://news.cctv.com/2019/07/gaiban/cmsdatainterface/page/world_3.jsonp"
        )
        ListType = "json_extract"
        ListConfig = @{
            items_path = "data.list"
            deduplicate_by = "url"
            fields = @{
                title = "title"
                url = "url"
                listing_url = "url"
                observed_at = "focus_date"
            }
        }
        DetailFields = @{
            detail_title = "h1"
            content = @{
                script_variable = "contentdate"
                selector = 'p:not([style*="text-align: center"])'
                attribute = "text"
                all = $true
                separator = "`n`n"
            }
            author = @{ selector = 'meta[name="author"]'; attribute = "content" }
            published_at = ".info"
            origin_source = @{ selector = 'meta[name="source"]'; attribute = "content"; default = $cctvNews }
        }
    },
    @{
        Name = "$xinhuanet$hotspot"
        Source = $xinhuanet
        MaxItems = 300
        ForceHttp = $true
        Urls = @(
            "https://www.news.cn/",
            "https://www.news.cn/politics/",
            "https://www.news.cn/world/",
            "https://www.news.cn/fortune/",
            "https://www.news.cn/tech/",
            "https://www.news.cn/local/"
        )
        ListType = "html_extract"
        ListConfig = @{
            item_selector = 'a[href*="/2026"][href$=".html"]:not(:has(img)):not(:empty)'
            deduplicate_by = "url"
            fields = @{
                title = @{ selector = ""; attribute = "text" }
                url = @{ selector = ""; attribute = "href" }
                listing_url = @{ selector = ""; attribute = "href" }
            }
        }
        DetailFields = @{
            detail_title = "h1"
            content = @{ selector = "#detailContent p"; attribute = "text"; all = $true; separator = "`n`n" }
            author = '.author, [class*="author-name"]'
            source_author_id = @{ selector = 'meta[name="author"]'; attribute = "content" }
            published_at = ".info"
            origin_source = ".source"
        }
    }
)

$existing = @()
foreach ($flow in (Invoke-SiftLaneJson -Method "GET" -Uri "$ApiBase/api/v1/flows")) {
    $existing += $flow
}
foreach ($spec in $specs) {
    $definition = New-NewsFlowDefinition $spec
    $body = $definition | ConvertTo-Json -Depth 30 -Compress
    $current = $existing | Where-Object { $_.name -eq $spec.Name } | Sort-Object revision -Descending | Select-Object -First 1
    if ($null -eq $current) {
        $updated = Invoke-SiftLaneJson -Method "POST" -Uri "$ApiBase/api/v1/flows" -Body $body
    }
    else {
        $uri = "$ApiBase/api/v1/flows/$($current.id)?expectedRevision=$($current.revision)"
        $updated = Invoke-SiftLaneJson -Method "PUT" -Uri $uri -Body $body
    }
    Write-Output "$($updated.name): revision $($updated.revision), $($updated.nodes.Count) nodes"
}
