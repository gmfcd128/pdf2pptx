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
