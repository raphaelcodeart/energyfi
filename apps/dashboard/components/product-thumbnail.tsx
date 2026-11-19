"use client";

/** Product image used everywhere, with one shared placeholder (package icon
    on a soft gradient) when there is no photo. */
export function ProductThumbnail({
  imageUrl,
  alt,
  className = "w-full h-full object-cover",
  iconClassName = "w-10 h-10 text-brand-400/40",
}: {
  imageUrl: string | null | undefined;
  alt: string;
  className?: string;
  iconClassName?: string;
}) {
  if (imageUrl) {
    // eslint-disable-next-line @next/next/no-img-element -- admin-supplied/uploaded URLs, not part of the Next asset pipeline
    return <img src={imageUrl} alt={alt} className={className} />;
  }
  return (
    <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-brand-500/10 to-accent-500/10">
      <svg className={iconClassName} fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
        />
      </svg>
    </div>
  );
}
