using Microsoft.AspNetCore.Mvc;
using Pdf2Pptx.Api.Models;
using Pdf2Pptx.Api.Services;

namespace Pdf2Pptx.Api.Controllers;

[ApiController]
[Route("api/conversions")]
public sealed class ConversionsController(IPdfConversionClient conversionClient) : ControllerBase
{
    private const string PptxMediaType =
        "application/vnd.openxmlformats-officedocument.presentationml.presentation";

    // Kestrel's own MaxRequestBodySize (configured in Program.cs) is the primary
    // guard; RequestFormLimits/RequestSizeLimit are set to the same ceiling so the
    // limit is visible right next to the endpoint that needs it, not just buried
    // in startup config.
    private const long MaxUploadBytes = 200_000_000;

    /// <summary>Accepts a PDF upload and forwards it to the Python service, which
    /// queues it for conversion and returns immediately (202) -- the actual
    /// conversion runs on Python's background worker; poll GetStatus for
    /// progress.</summary>
    [HttpPost]
    [RequestSizeLimit(MaxUploadBytes)]
    [RequestFormLimits(MultipartBodyLengthLimit = MaxUploadBytes)]
    public async Task<IActionResult> SubmitConversion(IFormFile? file, CancellationToken ct)
    {
        if (file is null || file.Length == 0)
        {
            return BadRequest(new ErrorResponse("No file was uploaded"));
        }
        if (!file.FileName.EndsWith(".pdf", StringComparison.OrdinalIgnoreCase))
        {
            return BadRequest(new ErrorResponse("Only .pdf uploads are accepted"));
        }

        var result = await conversionClient.SubmitAsync(file, ct);

        // Discard Python's own status_url (it's rooted at the Python container's
        // internal address) and rebuild one rooted at this API instead, so the
        // browser never sees or needs to know the Python service exists.
        var response = new ConversionAcceptedResponse(
            result.JobId, result.Status, $"/api/conversions/{result.JobId}");
        return AcceptedAtAction(nameof(GetStatus), new { jobId = result.JobId }, response);
    }

    /// <summary>Polls conversion progress. `error` is populated (with `status`
    /// "failed") if the conversion itself failed -- that's reported here as
    /// ordinary response data, not as an HTTP error, since the status query
    /// itself succeeded.</summary>
    [HttpGet("{jobId}")]
    public async Task<IActionResult> GetStatus(string jobId, CancellationToken ct)
    {
        var job = await conversionClient.GetJobAsync(jobId, ct);
        var resultUrl = job.Status == JobStatus.Done ? $"/api/conversions/{jobId}/result" : null;
        return Ok(new JobStatusResponse(job.JobId, job.Status, job.Progress, job.Error, resultUrl));
    }

    /// <summary>Streams the finished PPTX straight through from the Python
    /// service without buffering it in this process.</summary>
    [HttpGet("{jobId}/result")]
    public async Task<IActionResult> GetResult(string jobId, CancellationToken ct)
    {
        var upstream = await conversionClient.GetResultAsync(jobId, ct);
        // The HttpResponseMessage must stay alive for as long as its content
        // stream is being read (FileStreamResult streams chunks to the client as
        // they arrive from upstream, it doesn't read it all up front), but also
        // must eventually be disposed to release the underlying connection --
        // registering it against the response defers that dispose until this
        // response finishes writing, instead of leaking it or disposing too early.
        HttpContext.Response.RegisterForDispose(upstream);
        var stream = await upstream.Content.ReadAsStreamAsync(ct);
        var fileName = upstream.Content.Headers.ContentDisposition?.FileNameStar
            ?? upstream.Content.Headers.ContentDisposition?.FileName
            ?? $"{jobId}.pptx";

        return new FileStreamResult(stream, PptxMediaType) { FileDownloadName = fileName.Trim('"') };
    }
}
