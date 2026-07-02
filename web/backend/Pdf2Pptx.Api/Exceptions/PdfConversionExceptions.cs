using System.Net;

namespace Pdf2Pptx.Api.Exceptions;

/// <summary>The Python conversion service could not be reached at all (connection
/// refused, DNS failure, etc.) -- as opposed to it responding with an error status,
/// which is handled via the more specific exceptions below.</summary>
public sealed class UpstreamServiceUnavailableException(string message, Exception? inner = null)
    : Exception(message, inner);

/// <summary>A call to the Python service exceeded its per-endpoint time budget (see
/// PdfConversionClient's per-call CancellationTokenSource timeouts). Distinguished
/// from the client aborting the request themselves, which should not surface as a
/// server error.</summary>
public sealed class UpstreamTimeoutException(string message, Exception? inner = null)
    : Exception(message, inner);

/// <summary>Python returned 404 -- job id not found in its in-memory JobStore
/// (unknown id, or the service has since restarted and lost it).</summary>
public sealed class JobNotFoundException(string jobId)
    : Exception($"Unknown job id: {jobId}");

/// <summary>Python returned 409 on GET /jobs/{id}/result -- the job exists but
/// hasn't reached the "done" status yet.</summary>
public sealed class JobNotFinishedException(string detail)
    : Exception(detail);

/// <summary>Python responded with some other non-success status this client
/// doesn't special-case (e.g. its own 400 validation, or a 500). Carries the
/// original status code through so the middleware can pass it on as-is instead
/// of flattening every upstream error into a generic 503.</summary>
public sealed class PythonServiceException(HttpStatusCode statusCode, string message)
    : Exception(message)
{
    public HttpStatusCode StatusCode { get; } = statusCode;
}
