using System.Text.Json;
using System.Text.Json.Serialization;

namespace Pdf2Pptx.Api.Models;

/// <summary>DTOs returned to the browser. Property names are camelCase on the
/// wire (System.Text.Json's default web naming policy, configured in
/// Program.cs) to match ordinary JS/TS conventions on the Vue side.</summary>

public sealed record ConversionAcceptedResponse(string JobId, string Status, string StatusUrl);

public sealed record JobStatusResponse(
    string JobId,
    string Status,
    string? Progress,
    string? Error,
    string? ResultUrl);

public sealed record ErrorResponse(string Error);

/// <summary>One editable slide for the browser's PPTist editor: BackgroundImage/
/// OriginalImage are full URLs rooted at this API (rewritten from Python's
/// job-relative paths, same trick SubmitConversion applies to status_url),
/// BackgroundImage carrying a `?v=` cache-busting query so the browser refetches
/// it after a manual inpaint/revert swaps the underlying file. Elements is
/// forwarded verbatim -- already PPTist PPTTextElement-shaped JSON from Python.</summary>
public sealed record SlideDto(
    string Id,
    int PageIndex,
    int SourceWidth,
    int SourceHeight,
    string BackgroundImage,
    string OriginalImage,
    JsonElement Elements);

public sealed record SlidesResponse(double ViewportRatio, List<SlideDto> Slides);

public sealed record InpaintRequest(List<List<double>> Points, string Source);

public sealed record BackgroundImageResponse(string BackgroundImage);
