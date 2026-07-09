import React from "react";
import OfficialHeader from "@site/src/components/OfficialHeader";

interface NavbarProps {
    currentLocale?: string;
    hideLanguageSwitcher?: boolean;
}

const Navbar: React.FC<NavbarProps> = ({
    currentLocale,
    hideLanguageSwitcher: _hideLanguageSwitcher,
}) => {
    return <OfficialHeader currentLocale={currentLocale} />;
};

export default Navbar;
