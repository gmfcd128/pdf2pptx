using Microsoft.AspNetCore.Mvc;
using Pdf2Pptx.Api.Services;

namespace Pdf2Pptx.Api.Controllers;

[ApiController]
[Route("api/health")]
public sealed class HealthController(IPdfConversionClient conversionClient) : ControllerBase
{
    /// <summary>Reports this API's own liveness plus whether it can currently
    /// reach the Python conversion service -- useful for confirming the Docker
    /// network/service-name wiring between the two containers is correct.</summary>
    [HttpGet]
    public async Task<IActionResult> Get(CancellationToken ct)
    {
        var conversionServiceReachable = await conversionClient.IsHealthyAsync(ct);
        return Ok(new { status = "ok", conversionServiceReachable });
    }
}
