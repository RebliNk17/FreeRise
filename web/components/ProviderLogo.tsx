import { providerLogo, providerName } from "@/lib/providers";

/**
 * Logo tile that fills its parent box (size it with a wrapper, e.g. size-10). White ground with a subtle
 * border in both themes: the logos are designed for white.
 */
export function ProviderLogo({ provider }: { provider: string }) {
  const name = providerName(provider);
  const src = providerLogo(provider);
  const tile = "block size-full rounded-[30%] border border-[#efe7da] bg-white"; // white in both themes
  if (!src)
    return (
      <svg role="img" aria-label={name} viewBox="0 0 40 40" className={tile}>
        <text x="20" y="26.5" textAnchor="middle" fontSize="18" fontWeight="700" fill="#6b746f">
          {name.replace(/^בנק /, "").charAt(0)}
        </text>
      </svg>
    );
  // eslint-disable-next-line @next/next/no-img-element -- tiny static files; next/image adds nothing here
  return <img src={src} alt={name} className={`${tile} object-contain p-[3px]`} decoding="async" />;
}
