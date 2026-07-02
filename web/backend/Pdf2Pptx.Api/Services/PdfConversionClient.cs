using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using Pdf2Pptx.Api.Exceptions;
using Pdf2Pptx.Api.Models;

namespace Pdf2Pptx.Api.Services;

/// <summary>
/// Talks to the Python FastAPI conversion service (service/main.py). The
/// multi-minute PDF-to-PPTX conversion itself runs on Python's own background
/// worker -- POST /convert returns 202 as soon as Python finishes writing the
/// upload to disk, and callers are expected to poll GET /jobs/{id}. So no single
/// HTTP call made here ever blocks for the 1-3 minutes a conversion can take; the
/// per-call timeouts below are sized for network/file-transfer time (upload and
/// download bodies), not GPU time.
///
/// HttpClient.Timeout is left at Timeout.InfiniteTimeSpan (set where this is
/// registered in Program.cs) because it's a single blunt value that would apply
/// to every call including the sub-second /health and /jobs/{id} polls -- each
/// call here instead gets its own budget via a linked CancellationTokenSource.
/// </summary>
public sealed class PdfConversionClient(HttpClient httpClient, ILogger<PdfConversionClient> logger)
    : IPdfConversionClient
{
    private static readonly TimeSpan HealthTimeout = TimeSpan.FromSeconds(5);
    private static readonly TimeSpan UploadTimeout = TimeSpan.FromMinutes(5);
    private static readonly TimeSpan StatusTimeout = TimeSpan.FromSeconds(10);
    private static readonly TimeSpan DownloadTimeout = TimeSpan.FromMinutes(5);

    public async Task<bool> IsHealthyAsync(CancellationToken ct)
    {
        using var cts = LinkedTimeout(ct, HealthTimeout);
        try
        {
            using var response = await httpClient.GetAsync("/health", cts.Token);
            return response.IsSuccessStatusCode;
        }
        catch (HttpRequestException)
        {
            return false;
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            return false;
        }
    }

    public async Task<PythonConvertResponse> SubmitAsync(IFormFile file, CancellationToken ct)
    {
        using var cts = LinkedTimeout(ct, UploadTimeout);
        try
        {
            await using var fileStream = file.OpenReadStream();
            using var content = new MultipartFormDataContent();
            using var streamContent = new StreamContent(fileStream);
            streamContent.Headers.ContentType = string.IsNullOrEmpty(file.ContentType)
                ? new MediaTypeHeaderValue("application/pdf")
                : new MediaTypeHeaderValue(file.ContentType);

            // Not content.Add(streamContent, "file", file.FileName): that convenience
            // overload has .NET encode a non-ASCII filename (Chinese source filenames
            // are the norm for this tool) as RFC 5987 (`filename*=UTF-8''...`) instead
            // of a plain `filename="..."` parameter. Python's multipart parser (and
            // most others) doesn't understand that form and falls back to an empty
            // filename, which then fails *Python's* own ".pdf" extension check --
            // even though the filename arrived at this API correctly. Setting the
            // header directly sends the raw UTF-8 filename the way curl/browsers/
            // requests all do, which every multipart parser actually expects.
            streamContent.Headers.Remove("Content-Disposition");
            streamContent.Headers.TryAddWithoutValidation(
                "Content-Disposition",
                $"form-data; name=\"file\"; filename=\"{EscapeHeaderValue(file.FileName)}\"");
            content.Add(streamContent);

            using var response = await httpClient.PostAsync("/convert", content, cts.Token);
            await ThrowIfErrorAsync(response, cts.Token);

            return await response.Content.ReadFromJsonAsync<PythonConvertResponse>(cancellationToken: cts.Token)
                ?? throw new UpstreamServiceUnavailableException("Conversion service returned an empty response");
        }
        catch (HttpRequestException ex)
        {
            throw new UpstreamServiceUnavailableException("Conversion service is unavailable", ex);
        }
        catch (OperationCanceledException ex) when (!ct.IsCancellationRequested)
        {
            throw new UpstreamTimeoutException("Timed out uploading to the conversion service", ex);
        }
    }

    public async Task<PythonJobResponse> GetJobAsync(string jobId, CancellationToken ct)
    {
        using var cts = LinkedTimeout(ct, StatusTimeout);
        try
        {
            using var response = await httpClient.GetAsync($"/jobs/{Uri.EscapeDataString(jobId)}", cts.Token);
            await ThrowIfErrorAsync(response, cts.Token, jobId);

            return await response.Content.ReadFromJsonAsync<PythonJobResponse>(cancellationToken: cts.Token)
                ?? throw new UpstreamServiceUnavailableException("Conversion service returned an empty response");
        }
        catch (HttpRequestException ex)
        {
            throw new UpstreamServiceUnavailableException("Conversion service is unavailable", ex);
        }
        catch (OperationCanceledException ex) when (!ct.IsCancellationRequested)
        {
            throw new UpstreamTimeoutException($"Timed out fetching status for job {jobId}", ex);
        }
    }

    public async Task<HttpResponseMessage> GetResultAsync(string jobId, CancellationToken ct)
    {
        using var cts = LinkedTimeout(ct, DownloadTimeout);
        try
        {
            var request = new HttpRequestMessage(HttpMethod.Get, $"/jobs/{Uri.EscapeDataString(jobId)}/result");
            // ResponseHeadersRead: don't wait for (or buffer) the full PPTX body here --
            // the caller streams it straight through to the browser.
            var response = await httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cts.Token);
            try
            {
                await ThrowIfErrorAsync(response, cts.Token, jobId);
            }
            catch
            {
                response.Dispose();
                throw;
            }
            return response;
        }
        catch (HttpRequestException ex)
        {
            throw new UpstreamServiceUnavailableException("Conversion service is unavailable", ex);
        }
        catch (OperationCanceledException ex) when (!ct.IsCancellationRequested)
        {
            throw new UpstreamTimeoutException($"Timed out downloading result for job {jobId}", ex);
        }
    }

    private async Task ThrowIfErrorAsync(HttpResponseMessage response, CancellationToken ct, string? jobId = null)
    {
        if (response.IsSuccessStatusCode) return;

        var detail = await ReadErrorDetailAsync(response, ct);
        switch (response.StatusCode)
        {
            case HttpStatusCode.NotFound when jobId is not null:
                throw new JobNotFoundException(jobId);
            case HttpStatusCode.Conflict when jobId is not null:
                throw new JobNotFinishedException(detail ?? $"Job {jobId} is not finished yet");
            default:
                logger.LogWarning("Python service returned {StatusCode}: {Detail}", response.StatusCode, detail);
                throw new PythonServiceException(
                    response.StatusCode, detail ?? $"Conversion service returned {(int)response.StatusCode}");
        }
    }

    /// <summary>Escapes a filename for embedding in a quoted-string HTTP header
    /// parameter (RFC 6266 / RFC 2616 quoted-string): backslash and double-quote
    /// are the only characters that need it there.</summary>
    private static string EscapeHeaderValue(string value) =>
        value.Replace("\\", "\\\\").Replace("\"", "\\\"");

    private static async Task<string?> ReadErrorDetailAsync(HttpResponseMessage response, CancellationToken ct)
    {
        try
        {
            var error = await response.Content.ReadFromJsonAsync<PythonErrorResponse>(cancellationToken: ct);
            return error?.Detail;
        }
        catch
        {
            return null;
        }
    }

    private static CancellationTokenSource LinkedTimeout(CancellationToken ct, TimeSpan timeout)
    {
        var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(timeout);
        return cts;
    }
}
