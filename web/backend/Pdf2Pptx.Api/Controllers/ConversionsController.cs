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

    private const string PngMediaType = "image/png";

    /// <summary>Returns every page as a PPTist-ready editable slide. Image URLs
    /// are rewritten to route back through this API (never exposing the Python
    /// container's own address to the browser) and carry a `?v=` cache-busting
    /// query derived from the background file's current version, so the browser
    /// re-fetches it after a manual inpaint/restore-region.</summary>
    [HttpGet("{jobId}/slides")]
    public async Task<IActionResult> GetSlides(string jobId, CancellationToken ct)
    {
        var upstream = await conversionClient.GetSlidesAsync(jobId, ct);
        var slides = upstream.Slides.Select(s => new SlideDto(
            s.Id,
            s.PageIndex,
            s.SourceWidth,
            s.SourceHeight,
            $"/api/conversions/{jobId}/pages/{s.PageIndex}/background.png?v={s.BackgroundVersion}",
            $"/api/conversions/{jobId}/pages/{s.PageIndex}/original.png",
            s.Elements)).ToList();

        return Ok(new SlidesResponse(upstream.ViewportRatio, slides));
    }

    [HttpGet("{jobId}/pages/{pageIndex}/background.png")]
    public Task<IActionResult> GetPageBackground(string jobId, int pageIndex, CancellationToken ct) =>
        StreamPageImageAsync(jobId, pageIndex, "background", ct);

    [HttpGet("{jobId}/pages/{pageIndex}/original.png")]
    public Task<IActionResult> GetPageOriginal(string jobId, int pageIndex, CancellationToken ct) =>
        StreamPageImageAsync(jobId, pageIndex, "original", ct);

    /// <summary>Re-inpaints a user-drawn quadrilateral on one page, always
    /// sourced from the current background, and replaces that page's
    /// background with the result.</summary>
    [HttpPost("{jobId}/pages/{pageIndex}/inpaint")]
    public async Task<IActionResult> InpaintPageRegion(
        string jobId, int pageIndex, [FromBody] InpaintRequest request, CancellationToken ct)
    {
        var result = await conversionClient.InpaintPageRegionAsync(jobId, pageIndex, request.Points, ct);
        return Ok(new BackgroundImageResponse(
            $"/api/conversions/{jobId}/pages/{pageIndex}/background.png?v={result.BackgroundVersion}"));
    }

    /// <summary>Copies the original, un-inpainted page render's pixels into a
    /// user-drawn quadrilateral on the current background -- undoes
    /// auto/manual inpainting in just that region, not the whole page.</summary>
    [HttpPost("{jobId}/pages/{pageIndex}/restore-region")]
    public async Task<IActionResult> RestorePageRegion(
        string jobId, int pageIndex, [FromBody] InpaintRequest request, CancellationToken ct)
    {
        var result = await conversionClient.RestorePageRegionAsync(jobId, pageIndex, request.Points, ct);
        return Ok(new BackgroundImageResponse(
            $"/api/conversions/{jobId}/pages/{pageIndex}/background.png?v={result.BackgroundVersion}"));
    }

    private async Task<IActionResult> StreamPageImageAsync(string jobId, int pageIndex, string kind, CancellationToken ct)
    {
        var upstream = await conversionClient.GetPageImageAsync(jobId, pageIndex, kind, ct);
        HttpContext.Response.RegisterForDispose(upstream);
        var stream = await upstream.Content.ReadAsStreamAsync(ct);
        return new FileStreamResult(stream, PngMediaType);
    }
}
