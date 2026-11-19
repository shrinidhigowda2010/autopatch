import logoUrl from "../assets/logo.svg";

export default function Logo({ className = "h-9 w-auto", markOnly = false }: { className?: string; markOnly?: boolean }) {
  if (markOnly) {
    return (
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 44 56" className={className} aria-hidden>
        <path
          d="M22 2c0 0 16 4 16 4v22c0 12.5-8.2 22.8-16 26.5C14.2 50.8 6 40.5 6 28V6s16-4 16-4z"
          fill="#111111"
        />
        <path
          d="M16.2 20.4c1.6-1.6 4-1.9 5.9-.8l-2.2 2.2c-.5.5-.5 1.2 0 1.7l1.4 1.4c.5.5 1.2.5 1.7 0l2.2-2.2c1.1 1.9.8 4.3-.8 5.9-1.4 1.4-3.5 1.8-5.3 1.2l3.6 3.6c.5.5.5 1.3 0 1.8l-1.1 1.1c-.5.5-1.3.5-1.8 0l-7.8-7.8c-.5-.5-.5-1.3 0-1.8l1.1-1.1c.5-.5 1.3-.5 1.8 0l3.6 3.6c-.6-1.8-.2-3.9 1.2-5.3z"
          fill="#F5F0E6"
        />
        <path
          d="M23.8 34.2l3.2 3.2 7.4-8.2"
          stroke="#F5F0E6"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>
    );
  }
  return <img src={logoUrl} alt="Fixpilot" className={className} />;
}
