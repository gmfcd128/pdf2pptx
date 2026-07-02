using System.Text.Json.Serialization;
using Pdf2Pptx.Api.Middleware;
using Pdf2Pptx.Api.Services;

var builder = WebApplication.CreateBuilder(args);

// Kestrel's default MaxRequestBodySize (30MB) is well under the PDFs this API
// needs to accept (repo test fixtures already run up to ~18MB); 200MB gives
// headroom without being unbounded. The upload endpoint also carries its own
// [RequestSizeLimit]/[RequestFormLimits] (see ConversionsController) so the
// limit is visible next to the code that needs it, not just here.
builder.WebHost.ConfigureKestrel(options =>
{
    options.Limits.MaxRequestBodySize = 200_000_000;
});

builder.Services.AddControllers().AddJsonOptions(options =>
{
    options.JsonSerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull;
});
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

builder.Services.AddExceptionHandler<ConversionExceptionHandler>();
builder.Services.AddProblemDetails();

builder.Services.AddHttpClient<IPdfConversionClient, PdfConversionClient>(client =>
{
    var baseUrl = builder.Configuration["PythonService:BaseUrl"]
        ?? throw new InvalidOperationException("PythonService:BaseUrl is not configured");
    client.BaseAddress = new Uri(baseUrl);
    // No blanket timeout here -- PdfConversionClient budgets each call
    // individually via a linked CancellationTokenSource instead, since a single
    // HttpClient.Timeout would apply equally to a sub-second /health check and a
    // multi-minute file upload/download.
    client.Timeout = Timeout.InfiniteTimeSpan;
});

// Same-origin in the Docker/production path (nginx in the frontend container
// reverse-proxies /api to this service, so the browser never makes a
// cross-origin request at all) -- CORS is only needed as a convenience for
// hitting this API directly (Swagger UI, manual testing) during local
// non-Docker development, where the Vite dev server's own proxy (see
// web/frontend/vite.config.ts) already makes ordinary UI usage same-origin too.
const string DevCorsPolicy = "DevCors";
if (builder.Environment.IsDevelopment())
{
    builder.Services.AddCors(options =>
    {
        options.AddPolicy(DevCorsPolicy, policy =>
            policy.WithOrigins("http://localhost:5173").AllowAnyHeader().AllowAnyMethod());
    });
}

var app = builder.Build();

app.UseExceptionHandler();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
    app.UseCors(DevCorsPolicy);
}

app.MapControllers();

app.Run();
