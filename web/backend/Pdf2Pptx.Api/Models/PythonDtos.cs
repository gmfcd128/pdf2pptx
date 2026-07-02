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
