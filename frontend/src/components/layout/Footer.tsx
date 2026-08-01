import Link from "next/link";

export default function Footer() {
  return (
    <footer className="w-full py-xl px-lg bg-white/90 dark:bg-[#03050f]/80 backdrop-blur-md border-t border-black/5 dark:border-white/10 transition-colors duration-300 relative z-10">
      <div className="max-w-[1280px] mx-auto flex flex-col md:flex-row justify-between items-start md:items-center gap-xl">
        <div className="flex flex-col items-start">
          <span className="font-headline-md text-headline-md font-bold text-primary dark:text-white mb-sm">
            DocMind
          </span>
          <p className="font-body-sm text-body-sm text-on-background/60 dark:text-white/60">
            © 2026 Linnet AI Solutions. All rights reserved.
          </p>

        </div>
        <div className="flex flex-col gap-sm">
          <div className="flex items-center gap-lg">
            <a
              className="text-on-background/70 dark:text-white/70 hover:text-primary transition-colors flex items-center justify-center p-2 rounded-full bg-black/5 dark:bg-white/5"
              href="mailto:liuljima1896@gmail.com"
              title="Email Us"
            >
              <span className="material-symbols-outlined text-[20px]">mail</span>
            </a>
            <a
              className="text-on-background/70 dark:text-white/70 hover:text-primary transition-colors flex items-center justify-center p-2 rounded-full bg-black/5 dark:bg-white/5"
              href="https://www.linkedin.com/in/liul-j-teshome"
              target="_blank"
              rel="noreferrer"
              title="LinkedIn Profile"
            >
              <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24">
                <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z" />
              </svg>
            </a>
            <a
              className="text-on-background/70 dark:text-white/70 hover:text-primary transition-colors flex items-center justify-center p-2 rounded-full bg-black/5 dark:bg-white/5"
              href="https://x.com/linnet_ai"
              target="_blank"
              rel="noreferrer"
              title="X (Twitter) Profile"
            >
              <svg className="w-5 h-5 fill-current" viewBox="0 0 24 24">
                <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
              </svg>
            </a>
          </div>

        </div>
        <div className="flex gap-lg">
          <Link
            className="font-label-md text-label-md text-on-background/50 dark:text-white/50 hover:text-primary transition-colors"
            href="#"
          >
            Privacy Policy
          </Link>
          <Link
            className="font-label-md text-label-md text-on-background/50 dark:text-white/50 hover:text-primary transition-colors"
            href="#"
          >
            Terms
          </Link>
          <Link
            className="font-label-md text-label-md text-on-background/50 dark:text-white/50 hover:text-primary transition-colors"
            href="#"
          >
            Security
          </Link>
        </div>
      </div>
    </footer>
  );
}
