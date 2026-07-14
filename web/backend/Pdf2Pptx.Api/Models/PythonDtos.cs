using System.Text.Json;
using System.Text.Json.Serialization;

namespace Pdf2Pptx.Api.Models;

/// <summary>
/// Raw shapes returned by the Python service (service/main.py). Kept separate from
/// the DTOs we hand back to the browser (see ApiDtos.cs) so that Python's internal
/// status_url/result_url -- which point at the Python container's own address --
/// never leak through untouched; PdfConversionClient discards them and rebuilds
/// equivalents rooted at this API instead.
/// </summary>
public sealed class PythonConvertResponse
{
    [JsonPropertyName("job_id")]
    public required string JobId { get; init; }

    [JsonPropertyName("status")]
    public required string Status { get; init; }
}

public sealed class PythonJobResponse
{
    [JsonPropertyName("job_id")]
    public required string JobId { get; init; }

    [JsonPropertyName("status")]
    public required string Status { get; init; }

    [JsonPropertyName("progress")]
    public string? Progress { get; init; }

    [JsonPropertyName("error")]
    public string? Error { get; init; }
}

public sealed class PythonErrorResponse
{
    [JsonPropertyName("detail")]
    public string? Detail { get; init; }
}

/// <summary>One page's raw slide data as Python emits it: elements are already
/// PPTist-shaped, so they're passed through as an opaque JsonElement rather than
/// re-modeled here -- this API doesn't need to understand their internals, only
/// relay them and rewrite the two image paths into URLs rooted at itself.</summary>
public sealed class PythonSlideDto
{
    [JsonPropertyName("id")]
    public required string Id { get; init; }

    [JsonPropertyName("page_index")]
    public required int PageIndex { get; init; }

    [JsonPropertyName("source_width")]
    public required int SourceWidth { get; init; }

    [JsonPropertyName("source_height")]
    public required int SourceHeight { get; init; }

    [JsonPropertyName("background_version")]
    public required long BackgroundVersion { get; init; }

    [JsonPropertyName("elements")]
    public required JsonElement Elements { get; init; }
}

public sealed class PythonSlidesResponse
{
    [JsonPropertyName("viewport_ratio")]
    public required double ViewportRatio { get; init; }

    [JsonPropertyName("slides")]
    public required List<PythonSlideDto> Slides { get; init; }
}

/// <summary>Response shape shared by Python's inpaint and restore-region
/// endpoints.</summary>
public sealed class PythonBackgroundResponse
{
    [JsonPropertyName("background_path")]
    public required string BackgroundPath { get; init; }

    [JsonPropertyName("background_version")]
    public required long BackgroundVersion { get; init; }
}

/// <summary>Outgoing-only shape for POST .../inpaint and .../restore-region --
/// explicit property names regardless of any ambient serializer naming
/// policy, matching Python's RegionRequest pydantic model (service/main.py)
/// field-for-field.</summary>
public sealed class PythonRegionRequest
{
    [JsonPropertyName("points")]
    public required List<List<double>> Points { get; init; }
}
