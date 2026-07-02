# Multi-stage: SDK image builds/publishes, slimmer ASP.NET runtime image just runs.
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY Pdf2Pptx.Api.csproj .
RUN dotnet restore Pdf2Pptx.Api.csproj
COPY . .
RUN dotnet publish Pdf2Pptx.Api.csproj -c Release -o /app/publish --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime
WORKDIR /app
COPY --from=build /app/publish .

# Not 5000/5001 (ASP.NET Core's old dev defaults, often already bound by other
# local `dotnet run` instances) and not 80 (avoid running as a privileged port
# inside the container for no reason).
ENV ASPNETCORE_URLS=http://+:8080
EXPOSE 8080

ENTRYPOINT ["dotnet", "Pdf2Pptx.Api.dll"]
