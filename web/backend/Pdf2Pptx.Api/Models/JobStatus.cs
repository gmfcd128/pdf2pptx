namespace Pdf2Pptx.Api.Models;

/// <summary>
/// Mirrors service/jobs.py's JobStatus string enum exactly (values are the wire
/// format, lowercase, matching Python's `class JobStatus(str, enum.Enum)`).
/// </summary>
public static class JobStatus
{
    public const string Queued = "queued";
    public const string Processing = "processing";
    public const string Done = "done";
    public const string Failed = "failed";
}
