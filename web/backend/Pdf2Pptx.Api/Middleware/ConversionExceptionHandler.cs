using System.Net;
using Microsoft.AspNetCore.Diagnostics;
using Pdf2Pptx.Api.Exceptions;
using Pdf2Pptx.Api.Models;

namespace Pdf2Pptx.Api.Middleware;

/// <summary>
/// Central mapping from PdfConversionClient's exceptions to HTTP responses, so
/// controllers stay thin (just call the client and let unhandled exceptions
/// bubble up here) instead of repeating try/catch-and-map-status-code in every
/// action.
/// </summary>
public sealed class ConversionExceptionHandler(ILogger<ConversionExceptionHandler> logger) : IExceptionHandler
{
    public async ValueTask<bool> TryHandleAsync(HttpContext httpContext, Exception exception, CancellationToken ct)
    {
        var (statusCode, message) = exception switch
        {
            UpstreamServiceUnavailableException ex => (HttpStatusCode.ServiceUnavailable, ex.Message),
            UpstreamTimeoutException ex => (HttpStatusCode.GatewayTimeout, ex.Message),
            JobNotFoundException ex => (HttpStatusCode.NotFound, ex.Message),
            JobNotFinishedException ex => (HttpStatusCode.Conflict, ex.Message),
            PythonServiceException ex => (ex.StatusCode, ex.Message),
            _ => ((HttpStatusCode?)null, (string?)null),
        };

        if (statusCode is null)
        {
            return false; // not one of ours -- let the default developer/production error page handle it
        }

        if (statusCode == HttpStatusCode.ServiceUnavailable || statusCode == HttpStatusCode.GatewayTimeout)
        {
            logger.LogWarning(exception, "Conversion service call failed: {Message}", message);
        }

        httpContext.Response.StatusCode = (int)statusCode;
        await httpContext.Response.WriteAsJsonAsync(new ErrorResponse(message!), ct);
        return true;
    }
}
