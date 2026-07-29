import Link from "next/link";

export default function Footer() {
  return (
    <footer className="w-full py-xl px-lg bg-white/90 dark:bg-[#03050f]/80 backdrop-blur-md border-t border-black/5 dark:border-white/10 transition-colors duration-300 relative z-10">
      <div className="max-w-[1280px] mx-auto flex flex-col md:flex-row justify-between items-start md:items-center gap-xl">
        <div className="flex flex-col items-start">
          <span className="font-headline-md text-headline-md font-bold text-primary dark:text-white mb-sm">
            DocMind
          </span>
          <p className="font-body-sm text-body-sm text-on-background/50 dark:text-white/50">
            © 2024 DocMind Enterprise. All rights reserved.
          </p>
        </div>
        <div className="flex flex-col gap-sm">
          <div className="flex items-center gap-lg">
            <a
              className="text-on-background/70 dark:text-white/70 hover:text-primary transition-colors flex items-center justify-center p-2 rounded-full bg-black/5 dark:bg-white/5"
              href="mailto:liuljima1896@gmail.com"
              title="Email Us"
            >
              <span className="material-symbols-outlined text-[24px]">mail</span>
            </a>
            <a
              className="text-on-background/70 dark:text-white/70 hover:opacity-80 transition-opacity flex items-center justify-center"
              href="https://www.linkedin.com/in/liul-j-teshome"
              target="_blank"
              title="LinkedIn"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                alt="LinkedIn"
                className="w-8 h-8 object-contain"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuCXaPdSdfM4QF-axurJz82TZeBPC5Ir2xVDldy6-7j5zkiB0FJ1xG3FTyJIjox7mbV19MpX2k5iwTPO_5BMxlmg5g9SMS-BuYZwO3cQ2e3GQlXUVQWro5rBB9_MPE06EHmTCUcNOCllU-KJbSfYi6YqLBjz1SVPMu7iGnx6Cr3LFCPfJcCurBHkLZa2Bt81VHFTmkadqgo6cUzJs4YXrD7VnCIeS3zeCDMcM5OcYXbVOoOYc4Tm_TZxB0FxNtqLzj2Fua-cmdyOh-uH"
              />
            </a>
            <a
              className="text-on-background/70 dark:text-white/70 hover:opacity-80 transition-opacity flex items-center justify-center"
              href="https://x.com/linnet_ai"
              target="_blank"
              title="X (Twitter)"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                alt="X"
                className="w-8 h-8 object-contain"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuBUuwp5sq2UzK5Ea6TklttvBiDTN7NaQ71WqRR8oxcX6qRiF4yBDRUXIdO4FMIgYUZoG8XhcQfFvzh8SKLzL5WLPI0a55vIvmz5o9dABwqO18SS19D-JlVi9OMfUfGIuO0-7kucDUFFYRfrVkmjucnd9BLujv-yw4Z0_4DmBak-VN6kT-A3mNEslWNiF3202pnZQ2pV5oRG1PtAAMVtwo8XYANqqXR5mZv1sfhPxeIRYEjysNSeW9skkXJr9ppeW8arpaGnm6bvq-iW"
              />
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
