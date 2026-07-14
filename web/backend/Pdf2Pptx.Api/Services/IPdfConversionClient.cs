using Pdf2Pptx.Api.Models;

namespace Pdf2Pptx.Api.Services;

public interface IPdfConversionClient
{
    Task<bool> IsHealthyAsync(CancellationToken ct);

    Task<PythonConvertResponse> SubmitAsync(IFormFile file, CancellationToken ct);

    Task<PythonJobResponse> GetJobAsync(string jobId, CancellationToken ct);

    /// <summary>Returns the still-open upstream response so the caller can stream
    /// its content straight through to the browser without buffering the whole
    /// PPTX in this process. Caller is responsible for disposing it.</summary>
    Task<HttpResponseMessage> GetResultAsync(string jobId, CancellationToken ct);

    Task<PythonSlidesResponse> GetSlidesAsync(string jobId, CancellationToken ct);

    /// <summary>Returns the still-open upstream response for one page's
    /// background/original PNG -- same streaming contract as GetResultAsync.
    /// `kind` is "background" or "original".</summary>
    Task<HttpResponseMessage> GetPageImageAsync(string jobId, int pageIndex, string kind, CancellationToken ct);

    /// <summary>Re-inpaints a quadrilateral, always sourced from the page's
    /// current background.</summary>
    Task<PythonBackgroundResponse> InpaintPageRegionAsync(
        string jobId, int pageIndex, List<List<double>> points, CancellationToken ct);

    /// <summary>Copies the original page render's pixels into a quadrilateral
    /// on the current background -- a plain composite, not inpainting.</summary>
    Task<PythonBackgroundResponse> RestorePageRegionAsync(
        string jobId, int pageIndex, List<List<double>> points, CancellationToken ct);
}
