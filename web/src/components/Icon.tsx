export type IconName = "search" | "sparkle" | "pin" | "clock" | "tent" | "close" | "external" | "info" | "alert";

const PATHS: Record<IconName, string> = {
  search: "M11 4a7 7 0 1 0 4.2 12.6l4.1 4.1 1.4-1.4-4.1-4.1A7 7 0 0 0 11 4Zm0 2a5 5 0 1 1 0 10 5 5 0 0 1 0-10Z",
  sparkle: "M12 2l2.2 6.3L20.5 10l-6.3 1.7L12 18l-2.2-6.3L3.5 10l6.3-1.7L12 2Zm7 13l1 2.5 2.5 1-2.5 1-1 2.5-1-2.5-2.5-1 2.5-1 1-2.5Z",
  pin: "M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7Zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5Z",
  clock: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 5h-2v6l4.5 2.7 1-1.7-3.5-2V7Z",
  tent: "M12 3 2 20h20L12 3Zm0 5.5L17.6 18H6.4L12 8.5Z",
  close: "M6.4 5 5 6.4 10.6 12 5 17.6 6.4 19 12 13.4l5.6 5.6 1.4-1.4L13.4 12 19 6.4 17.6 5 12 10.6 6.4 5Z",
  external: "M14 3v2h3.6l-8.3 8.3 1.4 1.4L19 6.4V10h2V3h-7ZM5 5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5h-2v5H5V7h5V5H5Z",
  info: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm1 15h-2v-6h2v6Zm0-8h-2V7h2v2Z",
  alert: "M12 2 1 21h22L12 2Zm1 14h-2v-2h2v2Zm0-4h-2V9h2v3Z",
};

interface IconProps {
  name: IconName;
  size?: number;
}

// Decorative: the text next to an icon carries the meaning, so it is hidden
// from screen readers.
function Icon({ name, size = 20 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
      <path d={PATHS[name]} />
    </svg>
  );
}

export default Icon;
