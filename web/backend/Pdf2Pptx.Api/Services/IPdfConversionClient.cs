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
}
